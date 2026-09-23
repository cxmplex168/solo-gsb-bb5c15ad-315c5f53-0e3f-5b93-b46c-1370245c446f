"""邮件投递路径分析核心逻辑。

负责：
1. 处理邮件头部折行（folding / unfolding，RFC 5322 第 2.2.3 节）；
2. 提取全部 Received 字段及常见摘要字段；
3. 解析各跳时间（兼容 RFC 2822、ISO 8601 及常见非标准写法）；
4. 按时间先后排列中继节点，计算相邻节点耗时；
5. 无法解析或缺失时间的节点保留原始字段，标记为异常且不参与排序。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

# mbox 形式的信封首行（"From sender@example.com Wed Sep ..."）
_MBOX_FROM_RE = re.compile(r"^From \S+[ \t].+$")
# 字段名：可打印 ASCII，但不允许冒号
_HEADER_RE = re.compile(r"^([!-9;-~]+):[ \t]*(.*)$", re.S)
_COMMENT_RE = re.compile(r"\([^()]*\)")
_WS_RE = re.compile(r"\s+")

_FROM_RE = re.compile(r"\bfrom\s+(\S+)", re.IGNORECASE)
_BY_RE = re.compile(r"\bby\s+(\S+)", re.IGNORECASE)
_VIA_RE = re.compile(r"\bvia\s+(\S+)", re.IGNORECASE)
_WITH_RE = re.compile(r"\bwith\s+([A-Za-z0-9.-]+)", re.IGNORECASE)
_ID_RE = re.compile(r"\bid\s+([^\s;]+)", re.IGNORECASE)

GENERAL_HEADERS = ["From", "To", "Subject", "Date", "Message-ID", "Reply-To"]

# parsedate_to_datetime / fromisoformat 失败后的兜底格式
_FALLBACK_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S",
    "%d %b %Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M %z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S%z",
    "%Y/%m/%d %H:%M:%S",
]


class HeaderParseError(ValueError):
    """输入内容无法分析时抛出。"""


# --------------------------------------------------------------------------- #
# 折行处理与字段切分
# --------------------------------------------------------------------------- #
def unfold_headers(raw_text: str):
    """把原始头部展开为逻辑字段列表。

    返回 ``(headers, folded_count)``，其中 *headers* 为
    ``(字段名, 展开后的值, 展开后的原始行)`` 三元组，保持出现顺序；
    以空白字符开头的行视为上一行的折行续行。遇到空行表示头部结束。
    """
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and _MBOX_FROM_RE.match(lines[0]):
        lines = lines[1:]

    blocks: list[str] = []
    folded_count = 0
    for line in lines:
        if not line.strip():
            break  # 头部与正文之间的空行
        if line[0] in (" ", "\t") and blocks:
            folded_count += 1
            blocks[-1] += " " + line.strip()
        else:
            blocks.append(line)

    headers = []
    for block in blocks:
        match = _HEADER_RE.match(block)
        if not match:
            continue  # 跳过无法识别的杂散行，但不影响其他字段
        name = match.group(1).strip()
        value = _WS_RE.sub(" ", match.group(2)).strip()
        headers.append((name, value, _WS_RE.sub(" ", block).strip()))
    return headers, folded_count


# --------------------------------------------------------------------------- #
# 时间解析
# --------------------------------------------------------------------------- #
def _try_parse_datetime(value: str):
    candidate = value.strip().rstrip(".").strip()
    if not candidate:
        return None
    # 1) 标准 RFC 2822（含 UT/GMT/Z/EST 等旧式时区缩写）
    try:
        return parsedate_to_datetime(candidate)
    except (TypeError, ValueError):
        pass
    # 2) ISO 8601（Python 3.11 的 fromisoformat 已支持 Z，这里兼容旧写法）
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        pass
    # 3) 常见非标准格式兜底
    for fmt in _FALLBACK_FORMATS:
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    return None


def _strip_comments(value: str) -> str:
    previous = None
    while previous != value:  # 处理嵌套括号
        previous = value
        value = _COMMENT_RE.sub(" ", value)
    return value


def parse_received_date(date_raw):
    """解析 Received 分号后的时间部分。

    返回 ``(datetime|None, status, reasons)``：
    status 为 ``ok`` / ``warning`` / ``error``；
    reasons 为 ``(代码, 中文说明)`` 列表。原始时间始终保留在调用方。
    """
    if date_raw is None or not date_raw.strip():
        return None, "error", [("missing_date", "该节点缺少时间字段")]

    dt = _try_parse_datetime(date_raw)
    if dt is None:  # 去掉 "(PST)" 之类注释后再试一次
        stripped = _strip_comments(date_raw).strip()
        if stripped and stripped != date_raw.strip():
            dt = _try_parse_datetime(stripped)

    if dt is None:
        return None, "error", [("unparseable_date", "时间格式无法解析，已保留原文")]
    if not 1980 <= dt.year <= 2100:
        return None, "error", [("unparseable_date", f"时间年份异常（{dt.year}），已保留原文")]

    reasons = []
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        reasons.append(("naive_time", "未注明时区，已按 UTC 处理"))
    return dt, ("warning" if reasons else "ok"), reasons


# --------------------------------------------------------------------------- #
# Received 单跳解析
# --------------------------------------------------------------------------- #
def _split_received(value: str):
    """按最后一个分号拆分中继描述与时间（时间位于末尾）。"""
    pos = value.rfind(";")
    if pos == -1:
        return value, None
    return value[:pos], value[pos + 1:].strip() or None


def _find(pattern, text):
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip(".,;:")


def _build_hop(received_no: int, value: str) -> dict:
    chain_part, date_raw = _split_received(value)
    cleaned = _strip_comments(chain_part)
    dt, status, reasons = parse_received_date(date_raw)
    return {
        "idx": received_no - 1,           # 原始出现顺序（0 基，顶部为最新一跳）
        "received_no": received_no,       # 原始出现顺序（1 基）
        "from": _find(_FROM_RE, cleaned),
        "by": _find(_BY_RE, cleaned),
        "via": _find(_VIA_RE, cleaned),
        "protocol": _find(_WITH_RE, cleaned),
        "message_id": _find(_ID_RE, cleaned),
        "raw": value,                     # 原始（已展开）字段，始终保留
        "date_raw": date_raw,
        "status": status,
        "reasons": reasons,
        "_dt": dt,
    }


# --------------------------------------------------------------------------- #
# 展示辅助
# --------------------------------------------------------------------------- #
def humanize_delta(seconds):
    if seconds is None:
        return "—"
    total = abs(seconds)
    if total < 1:
        return f"{total * 1000:.0f} 毫秒"
    if total < 60:
        return f"{total:.1f} 秒"
    if total < 3600:
        return f"{int(total // 60)} 分 {int(total % 60)} 秒"
    if total < 86400:
        return f"{int(total // 3600)} 小时 {int((total % 3600) // 60)} 分"
    return f"{int(total // 86400)} 天 {int((total % 86400) // 3600)} 小时"


def _format_offset(dt: datetime):
    offset = dt.utcoffset()
    if offset is None:
        return None
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}{(total % 3600) // 60:02d}"


def _decode_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, ValueError):
        return value


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def analyze(raw_text: str, max_chars: int = 262_144) -> dict:
    if not raw_text or not raw_text.strip():
        raise HeaderParseError("请粘贴邮件原始头部内容后再分析。")
    if len(raw_text) > max_chars:
        raise HeaderParseError(
            f"输入过长：{len(raw_text)} 字符，上限为 {max_chars} 字符（可用 MAX_HEADER_CHARS 调整）。"
        )

    headers, folded_count = unfold_headers(raw_text)

    hops: list[dict] = []
    general: dict[str, str] = {}
    for name, value, _block in headers:
        if name.lower() == "received":
            hops.append(_build_hop(len(hops) + 1, value))
        elif name in GENERAL_HEADERS and name not in general:
            general[name] = _decode_value(value)

    # 可解析时间的节点按真实时间升序排列；时间相同保持原始顺序（稳定排序）。
    timed = [h for h in hops if h["_dt"] is not None]
    timed.sort(key=lambda h: (h["_dt"], h["idx"]))
    # 缺少 / 无法解析时间的节点无法定位，统一附在末尾并保持原始相对顺序。
    untimed = [h for h in hops if h["_dt"] is None]
    ordered = timed + untimed

    previous_dt = None
    for order, hop in enumerate(ordered, start=1):
        hop["order"] = order
        hop["sortable"] = hop["_dt"] is not None
        dt = hop["_dt"]
        if dt is None:
            hop["delta_seconds"] = None
            hop["delta_display"] = "—"
            continue

        if previous_dt is None:
            hop["delta_seconds"] = None
            hop["delta_display"] = "最早一跳"
        else:
            delta = (dt - previous_dt).total_seconds()
            hop["delta_seconds"] = delta
            hop["delta_display"] = humanize_delta(delta)
            # Received 自上而下为新→旧，故路径上越早的跳 idx 越大。
            # 时间排序后若相邻两跳 idx 反而递增，说明时间先后与记录顺序矛盾，
            # 通常由某台中继主机时钟偏差造成。
            prev_hop = ordered[order - 2]
            if prev_hop["_dt"] is not None and hop["idx"] > prev_hop["idx"]:
                hop["status"] = "warning"
                hop["reasons"].append(
                    ("time_order_conflict", "该节点时间与 Received 记录顺序矛盾，疑似中继主机时钟偏差")
                )
        previous_dt = dt

    # 中继链：第一跳的 from，后续依次取每跳的 by
    chain_nodes: list[str] = []
    for hop in timed:
        if not chain_nodes:
            chain_nodes.append(hop["from"] or "未知主机")
        chain_nodes.append(hop["by"] or "未知主机")

    span_seconds = None
    if len(timed) >= 2:
        span_seconds = (timed[-1]["_dt"] - timed[0]["_dt"]).total_seconds()

    # 序列化：统一转 UTC 展示，输出结构可直接 JSON 化
    for hop in ordered:
        dt = hop.pop("_dt")
        naive = any(code == "naive_time" for code, _msg in hop["reasons"])
        if dt is None:
            hop["datetime_iso"] = None
            hop["datetime_display"] = None
            hop["tz_display"] = None
        else:
            utc = dt.astimezone(timezone.utc)
            hop["datetime_iso"] = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            hop["datetime_display"] = utc.strftime("%Y-%m-%d %H:%M:%S UTC")
            hop["tz_display"] = "未注明（按 UTC 处理）" if naive else f"原始偏移 {_format_offset(dt)}"

    anomalies = sum(1 for h in ordered if h["status"] != "ok")
    return {
        "stats": {
            "total": len(hops),
            "resolved": len(timed),
            "unresolved": len(untimed),
            "anomalies": anomalies,
            "folded_lines": folded_count,
            "span_seconds": span_seconds,
            "span_display": humanize_delta(span_seconds) if span_seconds is not None else "—",
        },
        "chain": chain_nodes,
        "hops": ordered,
        "general": [{"key": key, "value": general.get(key)} for key in GENERAL_HEADERS],
    }
