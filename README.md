# DataCollector

DataCollector 是一个由 AI 驱动 Playwright 的交互式浏览器自动化助理。

项目将从原来的简易爬虫框架，重新定义为一个可以多轮对话、理解上下文、调用浏览器工具、清洗数据并导出产物的自动化工具。

## 当前目标

P0 阶段目标：

- 建立标准 Python 包结构。
- 使用 Playwright async Python 作为浏览器运行时。
- 使用 OpenAI Responses API 作为第一版工具调用接口。
- 以 Pydantic 模型定义任务、步骤、配置和运行结果。
- 提供 `dc chat` 入口进行交互式问答。
- 保留 `dc run` 作为一次性任务执行入口。

## 技术栈

- Python 3.12+
- Playwright async Python
- OpenAI Responses API
- Pydantic v2
- Pydantic AI
- Typer
- openpyxl
- reportlab
- uv

## 安装

```bash
uv sync
uv run playwright install
```

如果 Playwright 浏览器下载较慢，也可以直接使用本机已安装的 Chrome 或 Edge：

```bash
uv run dc chat "打开 example.com 并总结页面内容" \
  --url https://example.com \
  --headless \
  --browser-executable "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

复制环境变量示例：

```bash
cp .env.example .env
```

然后在 `.env` 中填写：

```bash
OPENAI_API_KEY=your_api_key
```

默认情况下，`OPENAI_API_KEY` 会访问 OpenAI 官方 API。也可以指定任何 OpenAI-compatible 服务，例如本地 Ollama、LM Studio、vLLM、Xinference 等：

```bash
OPENAI_API_KEY=local-placeholder
OPENAI_BASE_URL=http://localhost:11434/v1
DATACOLLECTOR_MODEL=qwen2.5:7b
DATACOLLECTOR_MODEL_API_STYLE=chat_completions
```

常见本地兼容服务示例：

```bash
# Ollama
OPENAI_BASE_URL=http://localhost:11434/v1
DATACOLLECTOR_MODEL=qwen2.5:7b
DATACOLLECTOR_MODEL_API_STYLE=chat_completions

# LM Studio
OPENAI_BASE_URL=http://localhost:1234/v1
DATACOLLECTOR_MODEL=local-model
DATACOLLECTOR_MODEL_API_STYLE=chat_completions

# vLLM
OPENAI_BASE_URL=http://localhost:8000/v1
DATACOLLECTOR_MODEL=Qwen/Qwen2.5-7B-Instruct
DATACOLLECTOR_MODEL_API_STYLE=chat_completions
```

如果本地服务不校验 key，`OPENAI_API_KEY` 也需要设置成任意非空占位值，例如 `local-placeholder`。

`DATACOLLECTOR_MODEL_API_STYLE` 可选：

- `responses`：OpenAI Responses API，默认值。
- `chat_completions`：OpenAI-compatible `/v1/chat/completions`，多数本地模型服务使用这个。

## 使用

推荐使用交互式模式：

```bash
uv run dc chat --headless --browser-executable "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

进入后可以直接对话：

```text
你: 搜索关键词：Playwright AI 自动化，帮我整理前 5 条结果
AI: ...

你: 继续找和 Python 相关的结果
AI: ...

你: 导出 Excel 和 Markdown
AI: 已导出：...
```

交互式模式支持会话命令：

```text
/open <url>              打开页面
/observe                 观察当前页面
/reset                   重置浏览器会话
/save-state [path]       保存登录态
/load-state <path>       加载登录态并重启会话
/help                    查看帮助
/exit                    退出
```

`dc chat` 会在同一个浏览器 page/context 中持续工作，所以可以先登录，再继续搜索、提取和导出。

也可以带第一条消息启动：

```bash
uv run dc chat "搜索关键词：Playwright AI 自动化，整理前 5 条结果" \
  --url https://www.bing.com \
  --headless \
  --browser-executable "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

会话会保存在 `runs/chat/<session_id>/`，包含对话历史、清洗后的 dataset 和导出的产物。

一次性任务仍然可以用 `dc run`：

```bash
uv run dc run "打开 example.com 并总结页面内容" --url https://example.com --headless
```

## P1 能力

当前版本已经包含第一批核心产品能力：

- 页面观察：URL、标题、文本摘要、可交互元素、链接、表格摘要和截图路径。
- 工具协议：所有 Playwright 工具返回统一的 `ToolResult`，包含成功状态、错误类型、当前 URL、截图路径和结构化数据。
- 结构化提取：支持提取页面文本、列表、表格、链接和媒体资源。
- 任务记忆：运行结果包含已完成动作、失败记录和提取数据。
- 安全控制：支持域名白名单 / 黑名单，并对删除、付款、提交、发送、账号变更等高风险操作要求确认。

可以通过 schema 文件提示 Agent 输出结构：

```bash
uv run dc run "提取商品列表" --url https://example.com --schema-file schema.json --headless
```

域名控制可以通过环境变量配置：

```bash
DATACOLLECTOR_ALLOWED_DOMAINS=example.com,example.org
DATACOLLECTOR_BLOCKED_DOMAINS=internal.example.com
```

## P2 能力

当前版本已经加入可靠性和开发体验能力：

- 每次运行保存 `metadata.json`、`events.jsonl`、`tool-calls.jsonl`、`artifacts.json`、`result.json`。
- 默认保存 Playwright trace：`trace.zip`。
- 默认写入 SQLite：`runs/datacollector.sqlite3`。
- 支持查询历史运行：

```bash
uv run dc list-runs
uv run dc show-run <run_id>
```

- 支持从 JSON 任务文件运行：

```bash
uv run dc run-file examples/task.json --headless
```

- 支持 TOML 配置文件：

```bash
uv run dc run-file examples/task.json --config datacollector.toml.example
```

- 浏览器高级能力已进入工具集：下载、上传、PDF、storage state、多标签页、多 context。

开发验证：

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check datacollector tests examples
```

## 交互式产物

`dc chat` 会把浏览器提取到的链接、列表、表格和媒体资源沉淀为结构化 dataset，并进行基础清洗：

- 去除空值。
- 统一空白字符。
- 去重。
- 将链接、列表项、表格行整理成统一行数据。

当前支持导出：

- Excel：`.xlsx`
- Markdown：`.md`
- PDF：`.pdf`
- CSV：`.csv`
- JSON：`.json`

## 需求文档

P0 到 P3 的需求优先级见：

- [docs/requirements-priority.md](docs/requirements-priority.md)
