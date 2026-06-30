from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from datacollector.agent.models import RunResult, TaskMemory, TaskSpec
from datacollector.chat import ChatSession
from datacollector.config import RuntimeConfig


class FakeRunner:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    async def run(self, task: TaskSpec) -> RunResult:
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

    reply = await session.ask("搜索 Alpha")
    export = await session.ask("导出 Excel 和 Markdown")

    assert reply.message == "已完成搜索。"
    assert len(session.history) == 4
    assert session.dataset.rows
    assert len(export.exports) == 2
    assert all(Path(item.path).exists() for item in export.exports)

