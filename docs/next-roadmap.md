# 下一阶段目标与待办重新评估

## 当前状态

项目已经完成从“简易爬虫框架”到“AI 驱动浏览器自动化助理”的基础改造。

已完成能力：

- 标准 Python 包结构和 `uv` 工程化。
- Playwright 浏览器运行时。
- AI 工具调用主循环。
- `dc chat` 交互式入口。
- 多轮文本上下文。
- 页面观察、点击、输入、滚动、截图、结构化提取等工具。
- 结构化数据沉淀和基础清洗。
- Excel / Markdown / PDF / CSV / JSON 导出。
- SQLite 运行历史。
- Playwright trace、截图、metadata、events、tool-calls 等可观测产物。
- OpenAI-compatible `base_url` 配置。
- 基础测试、fixture、示例和 lint。

## 重新评估后的核心问题

### 1. 交互式会话已升级为长期浏览器会话

当前 `dc chat` 已经能保留多轮文本上下文，并持有长期 `BrowserRuntime`。

已完成：

- 每轮对话复用同一个浏览器 page/context。
- 支持 `/open <url>` 打开页面。
- 支持 `/observe` 查看当前页面状态。
- 支持 `/reset` 重置浏览器会话。
- 支持 `/save-state` 保存登录态。
- 支持 `/load-state <path>` 复用登录态。
- `AgentRunner` 已支持复用外部 `BrowserRuntime`。

剩余问题：安全确认、模型适配和更强的数据清洗仍需继续推进。

### 2. OpenAI-compatible 支持还需要模型适配层

当前代码使用 OpenAI SDK 的 Responses API。

很多本地 OpenAI-compatible 服务只实现了：

- `/v1/chat/completions`
- Chat Completions 风格的 `tools`
- 或者甚至不完整支持工具调用

它们未必支持：

- `/v1/responses`
- Responses API 的 `function_call_output`
- `previous_response_id`

结论：仅有 `base_url` 还不够。必须抽象模型客户端，支持 Responses API 和 Chat Completions 两种协议。

### 3. 数据产物已经能导出，但还不够“可控”

当前数据清洗是基础规则：

- 去空值。
- 空白规范化。
- 去重。
- 链接 / 列表 / 表格转统一行。

但用户通常会继续要求：

- 重命名字段。
- 合并列。
- 去除广告或重复搜索结果。
- 按相关性排序。
- 只保留某些来源。
- 输出固定模板的 Markdown / PDF 报告。

结论：需要引入可配置的数据清洗管道和报告模板。

### 4. 安全确认机制还只是阻断，不是交互式确认

当前危险动作会被识别并阻断。

但理想行为应该是：

1. AI 告诉用户即将执行什么危险动作。
2. 用户输入确认。
3. 系统只放行被确认的那一步。
4. 确认记录进入日志。

结论：需要做真正的人类确认流程。

## 新优先级

## P0-Next：真实交互式浏览器会话

目标：让 `dc chat` 成为真正的浏览器自动化助理，而不是每轮启动一次任务。

- [x] 将 `ChatSession` 改为持有一个长期 `BrowserRuntime`。
- [x] 支持 `/open <url>` 打开页面。
- [x] 支持 `/observe` 查看当前页面状态。
- [x] 支持 `/reset` 重置浏览器会话。
- [x] 支持 `/save-state` 保存登录态。
- [x] 支持 `/load-state <path>` 复用登录态。
- [x] 每轮对话复用同一个 page/context。
- [x] 对话历史、浏览器状态、dataset、运行日志进入同一个 session 目录。
- [x] 修正 AgentRunner，使其既可独立运行，也可复用外部 BrowserRuntime。

验收标准：

- 用户可以先登录网站，再说“继续搜索 xxx”，浏览器不重启。
- 用户可以说“把刚才页面里的表格导出 Excel”，不需要重新打开页面。
- session 目录能完整记录对话、页面状态、截图、数据和导出产物。

## P1-Next：模型适配层

目标：真正支持 OpenAI 官方和本地 OpenAI-compatible 模型。

- [x] 新增 `ModelClient` 抽象。
- [x] 新增 `ResponsesModelClient`，用于 OpenAI Responses API。
- [x] 新增 `ChatCompletionsModelClient`，用于 `/v1/chat/completions`。
- [x] 配置项增加 `model.api_style`，可选 `responses` / `chat_completions`。
- [x] 对本地模型提供默认配置示例：
  - Ollama
  - LM Studio
  - vLLM
  - Xinference
- [ ] 如果模型不支持工具调用，给出清晰错误。
- [x] 增加 mock 测试覆盖两种协议。

验收标准：

- OpenAI 官方模型可继续使用。
- 本地兼容 `/v1/chat/completions` 的模型可以调用工具。
- 错误信息能区分：连不上服务、模型不存在、不支持工具调用、返回格式不兼容。

## P2-Next：交互式安全确认

目标：危险动作不是简单失败，而是进入用户确认流程。

- [ ] 定义 `PendingConfirmation` 模型。
- [ ] 工具执行遇到危险动作时返回确认请求。
- [ ] `dc chat` 显示待确认动作。
- [ ] 用户输入 `/yes` 或 `/no`。
- [ ] 只允许确认当前待执行动作。
- [ ] 确认结果写入 events 和 SQLite。

验收标准：

- AI 尝试点击“删除”时不会直接执行。
- 用户确认后才执行。
- 用户拒绝后 Agent 能继续寻找替代方案或停止。

## P3-Next：数据清洗和报告模板

目标：把“导出文件”升级为“生成可用报告”。

- [ ] 定义 `DataPipeline`。
- [ ] 支持字段选择、字段重命名、排序、去重规则。
- [ ] 支持用户用自然语言描述清洗要求。
- [ ] 支持 Markdown 报告模板。
- [ ] 支持 PDF 报告模板。
- [ ] Excel 增加多 sheet 输出：
  - 原始数据
  - 清洗后数据
  - 运行摘要
  - 来源链接
- [ ] 增加导出预览。

验收标准：

- 用户可以说“只保留标题、链接、摘要，按相关性排序，导出 Excel”。
- 导出的 Excel/Markdown/PDF 可以直接阅读或交付。

## P4-Next：服务化与 UI

目标：从本地 CLI 工具扩展为服务。

- [ ] FastAPI 服务。
- [ ] HTTP 提交会话消息。
- [ ] 查询会话状态。
- [ ] 下载产物。
- [ ] 流式返回步骤更新。
- [ ] Web UI 查看浏览器截图、步骤、数据和导出文件。

验收标准：

- 可以通过 HTTP 创建会话、发送消息、获取导出产物。
- Web UI 可以看到会话历史和运行产物。

## 建议执行顺序

1. **下一步做 P1-Next：模型适配层。**
   本地模型和 OpenAI-compatible 是项目的重要使用场景，不能只靠 `base_url`。

2. **再做 P2-Next：交互式安全确认。**
   浏览器自动化一定会遇到提交、删除、登录、发消息等高风险操作，确认流程要尽早建立。

3. **最后做 P3-Next：数据清洗与报告模板。**
   这会显著提升“最终产物”的价值，但应建立在稳定会话和模型适配之上。

## 当前最应该做的一件事

下一步应该实现：

> 抽象模型客户端，支持 Responses API 与 Chat Completions 两种工具调用协议。

这是让 OpenAI 官方模型和本地 OpenAI-compatible 模型都可用的关键一步。
