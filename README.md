# DataCollector

DataCollector 是一个由 AI 驱动 Playwright 的浏览器自动化运行时。

项目将从原来的简易爬虫框架，重新定义为一个可以接收自然语言任务、由 AI Agent 观察页面并调用 Playwright 工具执行操作的自动化工具。

## 当前目标

P0 阶段目标：

- 建立标准 Python 包结构。
- 使用 Playwright async Python 作为浏览器运行时。
- 使用 OpenAI Responses API 作为第一版工具调用接口。
- 以 Pydantic 模型定义任务、步骤、配置和运行结果。
- 提供 `dc` CLI 入口运行自然语言浏览器任务。

## 技术栈

- Python 3.12+
- Playwright async Python
- OpenAI Responses API
- Pydantic v2
- Pydantic AI
- Typer
- uv

## 安装

```bash
uv sync
uv run playwright install
```

如果 Playwright 浏览器下载较慢，也可以直接使用本机已安装的 Chrome 或 Edge：

```bash
uv run dc run "打开 example.com 并总结页面内容" \
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

## 使用

```bash
uv run dc run "打开 example.com 并总结页面内容" --url https://example.com --headed
```

或使用无头模式：

```bash
uv run dc run "打开 example.com 并总结页面内容" --url https://example.com --headless
```

运行结果会输出到终端，并在 `runs/` 目录保存 `result.json`、页面观察截图和执行产物。

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

## 需求文档

P0 到 P3 的需求优先级见：

- [docs/requirements-priority.md](docs/requirements-priority.md)
