from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from datacollector.agent import AgentRunner, RunResult, TaskSpec
from datacollector.artifacts import DataArtifact, DataCleaner, ExportResult
from datacollector.browser import BrowserRuntime, PageObservation
from datacollector.config import RuntimeConfig


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatReply(BaseModel):
    message: str
    run: RunResult | None = None
    exports: list[ExportResult] = Field(default_factory=list)
    observation: PageObservation | None = None


class ChatSession:
    def __init__(self, config: RuntimeConfig | None = None, session_dir: Path | None = None) -> None:
        self.config = config or RuntimeConfig.from_env()
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        self.session_dir = session_dir or (self.config.output_dir / "chat" / self.session_id)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.history: list[ChatMessage] = []
        self.runs: list[RunResult] = []
        self.dataset = DataArtifact(name=f"chat-{self.session_id}")
        self.runtime: BrowserRuntime | None = None
        self._observe_index = 0

    async def start(self) -> None:
        if self.runtime and self.runtime.browser:
            return
        self.runtime = BrowserRuntime(self.config.browser)
        await self.runtime.start()
        self._save_session()

    async def close(self) -> None:
        if self.runtime:
            await self.runtime.stop()
            self.runtime = None
        self._save_session()

    async def reset(self) -> None:
        await self.close()
        await self.start()

    async def ask(self, user_input: str, url: str | None = None) -> ChatReply:
        text = user_input.strip()
        self._append("user", text)

        command_reply = await self._handle_command(text)
        if command_reply:
            self._append("assistant", command_reply.message)
            self._save_session()
            return command_reply

        export_request = self._parse_export_request(text)
        if export_request:
            exports = self.export(export_request)
            message = "已导出：" + ", ".join(item.path for item in exports)
            self._append("assistant", message)
            self._save_session()
            return ChatReply(message=message, exports=exports)

        await self.start()
        assert self.runtime is not None
        task = TaskSpec(instruction=self._build_contextual_instruction(text), url=url)
        result = await AgentRunner(self.config).run_with_runtime(
            task,
            self.runtime,
            artifact_parent=self.session_dir / "runs",
        )
        self.runs.append(result)
        self._merge_result_data(result)

        message = result.final_message
        self._append("assistant", message)
        self._save_session()
        return ChatReply(message=message, run=result)

    def export(self, formats: list[str], output_stem: str | None = None) -> list[ExportResult]:
        stem = output_stem or "result"
        outputs: list[ExportResult] = []
        for item in formats:
            normalized = item.lower().strip(".")
            if normalized in {"md", "markdown"}:
                outputs.append(self.dataset.export_markdown(self.session_dir / f"{stem}.md"))
            elif normalized in {"xlsx", "excel"}:
                outputs.append(self.dataset.export_excel(self.session_dir / f"{stem}.xlsx"))
            elif normalized == "pdf":
                outputs.append(self.dataset.export_pdf(self.session_dir / f"{stem}.pdf"))
            elif normalized == "csv":
                outputs.append(self.dataset.export_csv(self.session_dir / f"{stem}.csv"))
            elif normalized == "json":
                outputs.append(self.dataset.export_json(self.session_dir / f"{stem}.json"))
            else:
                raise ValueError(f"unsupported export format: {item}")
        self._save_session()
        return outputs

    async def _handle_command(self, text: str) -> ChatReply | None:
        if not text.startswith("/"):
            return None
        command, _, rest = text.partition(" ")
        command = command.lower()
        argument = rest.strip()

        if command in {"/help", "/?"}:
            return ChatReply(message=self._help_text())

        if command == "/open":
            if not argument:
                return ChatReply(message="用法：/open <url>")
            await self.start()
            assert self.runtime is not None
            await self.runtime.require_page().goto(argument, wait_until="domcontentloaded")
            observation = await self._observe()
            return ChatReply(
                message=f"已打开：{observation.url}\n标题：{observation.title}",
                observation=observation,
            )

        if command == "/observe":
            await self.start()
            observation = await self._observe()
            return ChatReply(
                message=(
                    f"当前页面：{observation.url}\n"
                    f"标题：{observation.title}\n"
                    f"可交互元素：{len(observation.interactive_elements)} 个\n"
                    f"链接：{len(observation.links)} 个\n"
                    f"表格：{len(observation.tables)} 个"
                ),
                observation=observation,
            )

        if command == "/reset":
            await self.reset()
            return ChatReply(message="浏览器会话已重置。")

        if command == "/save-state":
            await self.start()
            assert self.runtime is not None
            path = Path(argument) if argument else self.session_dir / "storage-state.json"
            if not path.is_absolute():
                path = self.session_dir / path
            await self.runtime.save_storage_state(path)
            return ChatReply(message=f"登录态已保存：{path}")

        if command == "/load-state":
            if not argument:
                return ChatReply(message="用法：/load-state <path>")
            path = Path(argument)
            if not path.is_absolute():
                path = self.session_dir / path
            self.config.browser.storage_state = path
            await self.reset()
            return ChatReply(message=f"已加载登录态并重启浏览器会话：{path}")

        if command in {"/exit", "/quit"}:
            return ChatReply(message="请在 CLI 中使用 /exit 退出。")

        return ChatReply(message=f"未知命令：{command}。输入 /help 查看可用命令。")

    async def _observe(self) -> PageObservation:
        assert self.runtime is not None
        self._observe_index += 1
        screenshot_path = self.session_dir / "observations" / f"observe-{self._observe_index:03d}.png"
        return await self.runtime.observe(screenshot_path)

    def _build_contextual_instruction(self, current_input: str) -> str:
        recent = self.history[-10:]
        history_text = "\n".join(f"{message.role}: {message.content}" for message in recent)
        dataset_hint = ""
        if self.dataset.rows:
            dataset_hint = f"\n当前已沉淀 {len(self.dataset.rows)} 行结构化数据，可继续补充或清洗。"

        browser_hint = ""
        if self.runtime and self.runtime.page:
            browser_hint = f"\n当前浏览器页面 URL：{self.runtime.page.url}"

        return (
            "你正在一个多轮浏览器自动化问答会话中工作。\n"
            "请结合历史上下文和当前浏览器页面状态理解用户当前意图。\n"
            "如果信息不足，可以在最终回答中提出澄清问题。\n"
            "如果需要访问网页、搜索、点击、提取数据，请使用浏览器工具。\n\n"
            f"历史对话：\n{history_text}\n"
            f"{dataset_hint}"
            f"{browser_hint}\n\n"
            f"当前用户输入：{current_input}"
        )

    def _merge_result_data(self, result: RunResult) -> None:
        if not result.memory.extracted_data:
            return
        incoming = DataArtifact.from_extracted_data(
            result.memory.extracted_data,
            name=self.dataset.name,
        )
        self.dataset = DataArtifact(
            name=self.dataset.name,
            rows=DataCleaner.clean_rows([*self.dataset.rows, *incoming.rows]),
            notes=DataCleaner.clean_notes([*self.dataset.notes, *incoming.notes]),
        )

    def _append(self, role: str, content: str) -> None:
        self.history.append(ChatMessage(role=role, content=content))

    def _parse_export_request(self, text: str) -> list[str]:
        lowered = text.lower()
        if not any(keyword in lowered for keyword in ("导出", "export", "生成", "保存")):
            return []
        formats: list[str] = []
        if "excel" in lowered or "xlsx" in lowered or "表格" in text:
            formats.append("xlsx")
        if "markdown" in lowered or "md" in lowered or "文档" in text:
            formats.append("md")
        if "pdf" in lowered:
            formats.append("pdf")
        if "csv" in lowered:
            formats.append("csv")
        if "json" in lowered:
            formats.append("json")
        return formats

    def _save_session(self) -> None:
        current_page = None
        if self.runtime and self.runtime.page:
            current_page = self.runtime.page.url
        payload = {
            "session_id": self.session_id,
            "current_page": current_page,
            "history": [item.model_dump(mode="json") for item in self.history],
            "runs": [item.run_id for item in self.runs],
            "dataset": self.dataset.model_dump(mode="json"),
        }
        (self.session_dir / "session.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _help_text() -> str:
        return (
            "可用命令：\n"
            "/open <url> 打开页面\n"
            "/observe 观察当前页面\n"
            "/reset 重置浏览器会话\n"
            "/save-state [path] 保存登录态\n"
            "/load-state <path> 加载登录态并重启会话\n"
            "/exit 退出 CLI"
        )

