from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from datacollector.agent.models import RunResult, TaskMemory, TaskSpec
from datacollector.chat import ChatSession
from datacollector.config import RuntimeConfig


class FakeRunner:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    async def run_with_runtime(
        self,
        task: TaskSpec,
        runtime: object,
        artifact_parent: Path | None = None,
    ) -> RunResult:
        return RunResult(
            run_id="fake-run",
            success=True,
            task=task,
            started_at=datetime.now(),
            finished_at=datetime.now(),
            steps=[],
            memory=TaskMemory(
                goal=task.instruction,
                extracted_data=[
                    {
                        "tool": "extract_structured_data",
                        "data": {
                            "links": [{"text": "Alpha", "href": "https://example.com/a"}],
                        },
                    }
                ],
            ),
            final_message="已完成搜索。",
            artifact_dir=str(self.config.output_dir / "fake-run"),
        )


@pytest.mark.asyncio
async def test_chat_session_keeps_context_and_exports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("datacollector.chat.session.AgentRunner", FakeRunner)
    config = RuntimeConfig(output_dir=tmp_path)
    session = ChatSession(config, session_dir=tmp_path / "chat")

    async def fake_start() -> None:
        session.runtime = SimpleNamespace(browser=True, page=SimpleNamespace(url="about:blank"))

    async def fake_close() -> None:
        session.runtime = None

    monkeypatch.setattr(session, "start", fake_start)
    monkeypatch.setattr(session, "close", fake_close)

    reply = await session.ask("搜索 Alpha")
    export = await session.ask("导出 Excel 和 Markdown")

    assert reply.message == "已完成搜索。"
    assert len(session.history) == 4
    assert session.dataset.rows
    assert len(export.exports) == 2
    assert all(Path(item.path).exists() for item in export.exports)


@pytest.mark.asyncio
async def test_chat_session_reuses_browser_for_commands(
    edge_executable: str,
    tmp_path: Path,
) -> None:
    config = RuntimeConfig(output_dir=tmp_path)
    config.browser.headless = True
    config.browser.executable_path = edge_executable
    session = ChatSession(config, session_dir=tmp_path / "chat-browser")

    try:
        opened = await session.ask("/open data:text/html,<title>One</title><body>first</body>")
        observed = await session.ask("/observe")
        await session.ask("/open data:text/html,<title>Two</title><body>second</body>")

        assert opened.observation is not None
        assert opened.observation.title == "One"
        assert observed.observation is not None
        assert observed.observation.title == "One"
        assert session.runtime is not None
        assert session.runtime.page is not None
        assert await session.runtime.page.title() == "Two"
    finally:
        await session.close()

