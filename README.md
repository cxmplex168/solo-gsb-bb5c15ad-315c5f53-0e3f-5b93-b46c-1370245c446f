# 📮 MailTrace — 邮件投递路径检查器

一个轻量的 Python Flask 网页应用，帮助开发者检查邮件**原始头部**（raw headers）的投递路径：

- 自动处理 **折行（folding）字段**，按 RFC 5322 展开续行；
- 提取每一个 `Received` 字段中的时间戳，统一换算为 **UTC**；
- 按邮件**实际投递先后**排列中继节点（发件方 → 收件方），而不是按头部里的书写顺序；
- 计算并展示**相邻节点耗时**（含端到端总耗时）；
- **无法解析的时间标记为异常，但保留原始字段**（可展开查看）；
- **缺少时间的节点仍然列出**，不会被丢弃；
- 识别时钟偏移/时间倒灌（上一节点时间晚于本节点）并告警；
- 提取 `from` / `by` / `via` / `with` / `id` 与对端 IPv4/IPv6 地址。

解析核心（`mailtrace/`）仅依赖 Python 标准库，可脱离 Flask 单独使用或被其他程序导入。

---

## 一条命令启动

### 方式一：Docker Compose（推荐）

```bash
docker compose up -d --build
```

然后浏览器访问：

```
http://localhost:8000
```

### 方式二：仅用 Docker

```bash
docker build -t mailtrace . && docker run --rm -p 8000:8000 mailtrace
```

访问 `http://localhost:8000`。

> 容器在**启动时**会执行一次 `pip install -r requirements.txt`（见 `entrypoint.sh`），
> 因此即使基础镜像内没有预装依赖，依赖也会随容器启动自动安装；
> Dockerfile 在构建阶段也会预装一次以加速常规启动。
> 离线或希望跳过启动安装时，设置环境变量 `SKIP_STARTUP_INSTALL=1`。

停止服务：`docker compose down`。

---

## 使用方法

1. 打开 `http://localhost:8000`；
2. 把邮件的**原始头部**（Gmail 的“显示原始邮件”、Outlook 的“查看邮件来源”等）完整粘贴到文本框
   （也可以点“填入示例”）；
3. 点击 **分析投递路径**。

页面以时间线形式展示每个中继节点：节点名称、UTC 时间、from/by/协议、对端 IP、
距上一节点耗时、异常/告警，以及可展开的**原始 `Received` 文本（保留折行）**。

也提供 JSON 接口，便于脚本调用：

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"headers": "Received: by mx.example; Tue, 23 Sep 2026 10:00:00 +0800"}'
```

健康检查：`GET http://localhost:8000/healthz`。

---

## 排序原理（为什么要反转）

邮件每经过一台服务器，该服务器就把自己的 `Received` 字段**追加到头部最前面**。
因此头部文本里第一条 `Received` 是最后一跳（最靠近收件方），最后一条才是第一跳。
本工具按这一“嵌套结构”将 `Received` **反转**后呈现，得到真实投递顺序，
再用时间戳校验该顺序并计算相邻耗时。当解析出的时间出现倒挂（时钟偏差或伪造）时，会明确告警。

---

## 配置（环境变量）

| 变量 | 默认值 | 作用范围 | 说明 |
| --- | --- | --- | --- |
| `HOST_PORT` | `8000` | Compose | 宿主机映射端口（容器内服务固定监听 8000） |
| `APP_PORT` | `8000` | 容器/本地 | 容器内 gunicorn 绑定端口；改它需同步调整端口映射 |
| `APP_HOST` | `0.0.0.0` | 本地 | 直接用 Flask 开发服务器运行时的监听地址 |
| `MAX_INPUT_KB` | `256` | 容器/本地 | 单次粘贴头部的大小上限（KB），超出返回错误 |
| `SKIP_STARTUP_INSTALL` | `0` | 容器 | 设为 `1` 跳过容器启动时的 `pip install`，直接用镜像内依赖 |

### 访问端口

- Compose 默认把宿主机 **8000** 端口映射到容器 8000。
- 想换宿主机访问端口，在项目根目录创建 `.env`（或先导出环境变量再 `up`）：

```bash
echo "HOST_PORT=9000" > .env
docker compose up -d --build
# 访问 http://localhost:9000
```

也可以在运行时直接覆盖，例如：

```bash
docker run --rm -e MAX_INPUT_KB=512 -p 8080:8000 mailtrace
# 访问 http://localhost:8080
```

---

## 本地开发（不使用容器）

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python wsgi.py            # Flask 开发服务器，默认 http://localhost:8000
# 或
gunicorn -b 0.0.0.0:8000 wsgi:app
```

运行解析器测试（**仅需标准库，无需安装 Flask**）：

```bash
python -m unittest discover -s tests -v
```

---

## 项目结构

```
.
├── app/                    # Flask 应用（路由、模板）
│   ├── __init__.py         # create_app()：页面 + JSON API + 健康检查
│   └── templates/index.html
├── mailtrace/              # 纯标准库解析核心（可独立复用）
│   └── parsing/
│       ├── parser.py       # 折行展开、时间解析、路径排序、耗时与异常
│       └── sample.py       # 页面“填入示例”数据
├── wsgi.py                 # gunicorn / flask 启动入口
├── entrypoint.sh           # 容器启动时安装依赖并启动 gunicorn
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── tests/test_parser.py    # 解析核心单元测试
```

## 安全与隐私

应用只在本地/你的服务器内解析粘贴内容，不向任何外部服务发送邮件头；
请仍按敏感信息对待原始头部（其中可能含内网主机名与 IP）。
