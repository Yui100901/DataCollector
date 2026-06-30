from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from datacollector.agent.models import TaskSpec
from datacollector.agent.runner import AgentRunner
from datacollector.config import BrowserConfig, ModelConfig, RuntimeConfig


class FakeResponses:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_: object) -> object:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                id="response-1",
                output_text="",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        call_id="call-1",
                        name="extract_structured_data",
                        arguments=json.dumps({}),
                    )
                ],
            )
        return SimpleNamespace(id="response-2", output_text="done", output=[])


class FakeOpenAI:
    def __init__(self, **_: object) -> None:
        self.responses = FakeResponses()


@pytest.mark.asyncio
async def test_agent_loop_with_mocked_model(
    monkeypatch: pytest.MonkeyPatch,
    edge_executable: str,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("datacollector.agent.runner.AsyncOpenAI", FakeOpenAI)
    config = RuntimeConfig(
        browser=BrowserConfig(headless=True, executable_path=edge_executable),
        model=ModelConfig(api_key="test-key"),
        output_dir=tmp_path,
    )
    runner = AgentRunner(config)

    result = await runner.run(TaskSpec(instruction="extract", url="data:text/html,<h1>Hello</h1>"))

    assert result.success
    assert result.final_message == "done"
    assert result.memory.extracted_data
    assert (Path(result.artifact_dir) / "result.json").exists()

