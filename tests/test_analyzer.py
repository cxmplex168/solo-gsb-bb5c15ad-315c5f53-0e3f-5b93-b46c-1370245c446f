import pytest

from app import create_app
from app.analyzer import HeaderParseError, analyze, unfold_headers

SAMPLE_HEADERS = """\
Received: from mx.mailbox.org (mx.mailbox.org [198.51.100.20])
    by imap.mailbox.org with LMTP id 7mQ2AbCd12
    ; Tue, 23 Sep 2025 04:20:35 +0000 (UTC)
Received: from edge.mailbox.org (edge.mailbox.org [198.51.100.5])
    by mx.mailbox.org with ESMTP id 6pQ1ZyXx99
    ; Tue, 23 Sep 2025 04:20:33 +0000
Received: from scanner.example.net (scanner.example.net [203.0.113.50])
    by edge.mailbox.org with ESMTPS id 8nR0BcDe44
    ; Tue, 23 Sep 2025 04:20:32 +0000
Received: from mail.example.com (mail.example.com [203.0.113.10])
\tby scanner.example.net with ESMTP id 5oP9WvVu33;
\tTue, 23 Sep 2025 04:20:30 +0000
Received: from internal.lan (10.0.0.7)
\tby mail.example.com with SMTP id 4kL8Tt;
\tMon, 31 Sep 1981 09:00:00 +0000
Received: from workstation.local (192.168.1.5)
\tby internal.lan
\twith ESMTPA
Date: Tue, 23 Sep 2025 04:20:29 +0000
From: Alice <alice@example.com>
To: Bob <bob@mailbox.org>
Subject: =?UTF-8?B?5rWL6K+V5oiR5piv56ys5LiA5p2l?=
Message-ID: <20250923042029.AB12@example.com>
"""


def test_unfold_folded_headers():
    headers, folded = unfold_headers(SAMPLE_HEADERS)
    received = [(n, v) for n, v, _ in headers if n.lower() == "received"]
    assert len(received) == 6
    assert folded == 12  # 6 个 Received 共 12 行折行续行
    # 折行被展开为单空格，值中不含换行
    for _, value in received:
        assert "\n" not in value
    # from/by 跨折行仍可提取
    assert received[-1][1].endswith("with ESMTPA")


def test_analyze_orders_hops_by_time():
    result = analyze(SAMPLE_HEADERS)
    hops = result["hops"]
    assert result["stats"]["total"] == 6
    assert result["stats"]["resolved"] == 4
    assert result["stats"]["unresolved"] == 2

    # 最早一跳（原始 #4，04:20:30）排第一
    assert hops[0]["order"] == 1
    assert hops[0]["from"] == "mail.example.com"
    assert hops[0]["delta_display"] == "最早一跳"
    times = [h["datetime_iso"] for h in hops[:4]]
    assert times == sorted(times)
    assert hops[1]["delta_seconds"] == pytest.approx(2.0)
    assert hops[2]["delta_seconds"] == pytest.approx(1.0)
    assert hops[3]["delta_seconds"] == pytest.approx(2.0)
    assert hops[3]["by"] == "imap.mailbox.org"


def test_unparseable_and_missing_dates_are_kept():
    result = analyze(SAMPLE_HEADERS)
    bad_year, no_date = result["hops"][4], result["hops"][5]

    assert bad_year["sortable"] is False
    assert bad_year["status"] == "error"
    assert any(code == "unparseable_date" for code, _ in bad_year["reasons"])
    assert "1981" in bad_year["raw"]  # 原始字段保留
    assert bad_year["date_raw"].startswith("Mon, 31 Sep 1981")
    assert bad_year["delta_display"] == "—"

    assert no_date["sortable"] is False
    assert no_date["status"] == "error"
    assert any(code == "missing_date" for code, _ in no_date["reasons"])
    assert no_date["raw"] == "from workstation.local (192.168.1.5) by internal.lan with ESMTPA"
    assert result["chain"] == [
        "mail.example.com",
        "scanner.example.net",
        "edge.mailbox.org",
        "mx.mailbox.org",
        "imap.mailbox.org",
    ]


def test_naive_time_assumed_utc():
    headers = "Received: from a.example by b.example with SMTP; 23 Sep 2025 04:20:30\n"
    result = analyze(headers)
    hop = result["hops"][0]
    assert hop["status"] == "warning"
    assert any(code == "naive_time" for code, _ in hop["reasons"])
    assert hop["datetime_iso"] == "2025-09-23T04:20:30Z"


def test_timezone_conversion_and_deltas():
    # 06:20:30+0200 == 04:20:30 UTC；+0000 一跳晚 10 秒
    headers = (
        "Received: from b.example by c.example with SMTP;"
        " Tue, 23 Sep 2025 04:20:40 +0000\n"
        "Received: from a.example by b.example with SMTP;"
        " Tue, 23 Sep 2025 06:20:30 +0200\n"
    )
    result = analyze(headers)
    first, second = result["hops"]
    assert first["datetime_iso"] == "2025-09-23T04:20:30Z"
    assert first["tz_display"] == "原始偏移 +0200"
    assert second["delta_seconds"] == pytest.approx(10.0)


def test_clock_skew_warns_on_order_conflict():
    # 顶部（idx=0）时间反而早于下一跳（idx=1），时间先后与 Received 记录顺序矛盾，
    # 按时间排序后 idx=0 排第一、idx=1 排第二，触发时钟偏差告警。
    headers = (
        "Received: from b by c with SMTP; Tue, 23 Sep 2025 04:20:20 +0000\n"
        "Received: from a by b with SMTP; Tue, 23 Sep 2025 04:20:40 +0000\n"
    )
    result = analyze(headers)
    first, second = result["hops"]
    assert first["idx"] == 0 and second["idx"] == 1
    assert second["delta_seconds"] == 20.0
    assert second["status"] == "warning"
    assert "time_order_conflict" in [c for c, _ in second["reasons"]]


def test_iso8601_dates_supported():
    headers = (
        "Received: from a by b with SMTP; 2025-09-23T04:20:30+08:00\n"
        "Received: from b by c with SMTP; 2025-09-23T04:20:40Z\n"
    )
    result = analyze(headers)
    assert result["stats"]["resolved"] == 2
    # 04:20:30+08:00 == 前一天 20:20:30 UTC，应排在最前
    assert result["hops"][0]["datetime_iso"] == "2025-09-22T20:20:30Z"


def test_empty_and_oversized_input():
    with pytest.raises(HeaderParseError):
        analyze("   \n")
    with pytest.raises(HeaderParseError):
        analyze("Received: from a by b\n" + "x" * 2000, max_chars=100)


def test_mbox_separator_and_body_ignored():
    raw = (
        "From alice@example.com Tue Sep 23 04:20:00 2025\n"
        "Received: from a by b with SMTP; Tue, 23 Sep 2025 04:20:30 +0000\n"
        "Subject: hi\n\nbody line must be ignored\n"
    )
    result = analyze(raw)
    assert result["stats"]["total"] == 1
    assert result["general"][2]["value"] == "hi"  # Subject


def test_flask_routes():
    app = create_app()
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/healthz").get_json() == {"ok": True}

    resp = client.post("/api/analyze", json={"headers": SAMPLE_HEADERS})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["result"]["stats"]["resolved"] == 4

    bad = client.post("/api/analyze", json={"headers": ""})
    assert bad.status_code == 400
    assert bad.get_json()["ok"] is False

    page = client.post("/", data={"headers": SAMPLE_HEADERS})
    assert page.status_code == 200
    assert "中继链".encode() in page.data
