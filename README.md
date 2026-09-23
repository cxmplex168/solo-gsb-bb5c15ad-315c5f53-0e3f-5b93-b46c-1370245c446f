# 📮 邮件投递路径分析器（Received Header Inspector）

一个用于检查邮件**原始头部投递路径**的 Python Flask Web 应用。粘贴整段邮件头后，应用会：

1. **展开折行字段**——按 RFC 5322 规则处理 `Received` 等字段的换行折叠（folding/unfolding）；
2. **提取每一跳 Received**——解析 `from` / `by` / `via` / `with` / `id` 与末尾时间；
3. **解析各跳时间**——兼容 RFC 2822（`Tue, 23 Sep 2025 04:20:30 +0000`）、ISO 8601 及常见非标准写法，统一换算为 UTC；
4. **按实际先后排列中继节点**——时间升序还原真实投递路径，并计算**相邻节点耗时**；
5. **异常保留**——无法解析的时间（含异常年份）标记为「异常」并**保留原始字段**；缺少时间的节点**仍然列出**，附在表格末尾、不计入中继链；
6. 额外提示：未注明时区（按 UTC 处理）、时间先后与 Received 记录顺序矛盾（疑似主机时钟偏差）。

所有解析均在本地完成，粘贴内容不会发送到任何外部服务。

---

## 单条命令启动

需要已安装 Docker（含 Compose 插件）。在本项目目录执行：

```bash
docker compose up --build -d
```

然后浏览器访问：

```
http://localhost:8000
```

停止：

```bash
docker compose down
```

> **依赖安装时机：** 按设计，镜像构建时不预装 Python 依赖；容器**启动时**由
> `entrypoint.sh` 执行 `pip install -r requirements.txt`，随后启动 gunicorn。
> 因此首次启动需要数秒到十几秒（拉取 Flask / gunicorn）。

国内或内网环境可指定 PyPI 镜像加速启动时安装，编辑 `docker-compose.yml`
中被注释的 `environment`，或直接：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple docker compose up --build -d
```

> 注意：需在 compose 文件中声明 `PIP_INDEX_URL` 环境变量后上面的透传才生效，
> 也可直接取消文件内对应注释。

---

## 配置

通过容器环境变量配置（Compose 的 `environment` 段或 `docker run -e`）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_HOST` | `0.0.0.0` | gunicorn 监听地址 |
| `WEB_PORT` | `8000` | 容器内监听端口 |
| `GUNICORN_WORKERS` | `2` | gunicorn worker 数 |
| `MAX_HEADER_CHARS` | `262144` | 允许粘贴的头部最大字符数（约 256 KB） |
| `PIP_INDEX_URL` | 未设置 | 启动时装依赖使用的 PyPI 镜像地址 |

**宿主机访问端口**默认映射 `8000:8000`，可通过 `.env` 或环境变量改宿主机端口：

```bash
echo "WEB_PORT=9000" > .env && docker compose up --build -d   # 访问 http://localhost:9000
```

> 此时 `WEB_PORT` 同时影响容器内监听端口与映射；保持两者一致即可。

健康检查端点：`GET /healthz` → `{"ok": true}`。

---

## 使用方法

1. 在邮件客户端中打开「显示原始邮件 / 查看源代码 / Show Original」，复制完整头部；
2. 粘贴到首页文本框（或点「载入示例」），点击「分析投递路径」；
3. 查看：
   - **概览**：节点数、已解析/未解析数、异常数、投递总耗时、折行展开数；
   - **中继链**：`发件方 → … → 各中继 by → 最终信箱`；
   - **逐跳明细**：每跳 from/by、协议与 id、UTC 时间、距上一跳耗时、状态徽标，
     展开「原始 Received 字段」可查看该跳未改动的原文。

### JSON API

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"headers": "Received: from a by b with SMTP; Tue, 23 Sep 2025 04:20:30 +0000\n"}'
```

返回 `{"ok": true, "result": { "stats": ..., "chain": [...], "hops": [...], "general": [...] }}`；
输入为空或超长时返回 HTTP 400 与 `{"ok": false, "error": "..."}`。

---

## 本地开发（不使用 Docker）

要求 Python 3.11+：

```bash
pip install -r requirements.txt
python wsgi.py          # Flask 开发服务器，http://localhost:8000
# 或
gunicorn wsgi:app --bind 0.0.0.0:8000
```

运行测试（需额外安装 pytest）：

```bash
pip install -r requirements.txt pytest
python -m pytest tests/ -q
```

---

## 项目结构

```
.
├── app/
│   ├── __init__.py          # Flask 应用工厂与路由（页面 / JSON API / 健康检查）
│   ├── analyzer.py          # 折行展开、Received 提取、时间解析、排序与耗时计算
│   ├── static/style.css     # 页面样式
│   └── templates/index.html # 单页界面（表单、概览、中继链、逐跳明细）
├── tests/test_analyzer.py   # 解析与路由测试
├── wsgi.py                  # gunicorn 入口
├── entrypoint.sh            # 容器启动时安装依赖并启动 gunicorn
├── requirements.txt         # Flask、gunicorn
├── Dockerfile
└── docker-compose.yml
```

## 解析规则说明

- **折行**：以空格/Tab 开头的行拼接到上一逻辑行，空白折叠为单个空格；首个空行后的内容（正文）忽略；
  mbox 形式的首行 `From sender@...` 自动跳过。
- **Received 顺序**：邮件头中该字段自上而下为「新→旧」，但应用一律以**时间戳升序**还原投递先后，
  不依赖字段出现顺序；时间相同的节点保持原始相对顺序。
- **异常节点**：缺时间或时间无法解析/年份离谱（<1980 或 >2100）的节点不参与排序与耗时计算，
  置于明细表末尾并以分隔条注明，原始字段全文保留、可展开查看。
- **时钟偏差**：按时间排列后，若相邻节点的先后与 Received 记录顺序矛盾，标记「注意」。
