from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from datacollector.agent.models import TaskSpec
from datacollector.agent.runner import AgentRunner
from datacollector.config import BrowserConfig, ModelConfig, RuntimeConfig
from datacollector.models import ChatCompletionsModelClient


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


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_: object) -> object:
        self.calls += 1
        if self.calls == 1:
            message = SimpleNamespace(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="tool-call-1",
                        function=SimpleNamespace(
                            name="extract_structured_data",
                            arguments=json.dumps({}),
                        ),
                    )
                ],
            )
        else:
            message = SimpleNamespace(content="done", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAI:
    def __init__(self, **_: object) -> None:
        self.responses = FakeResponses()
        self.chat = SimpleNamespace(completions=FakeChatCompletions())


def fake_openai_with_chat_response(response: object) -> type:
    class FakeCustomChatCompletions:
        async def create(self, **_: object) -> object:
            return response

    class FakeCustomOpenAI:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(completions=FakeCustomChatCompletions())

    return FakeCustomOpenAI


@pytest.mark.asyncio
async def test_agent_loop_with_responses_model(
    monkeypatch: pytest.MonkeyPatch,
    edge_executable: str,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("datacollector.models.clients.AsyncOpenAI", FakeOpenAI)
    config = RuntimeConfig(
        browser=BrowserConfig(headless=True, executable_path=edge_executable),
        model=ModelConfig(api_key="test-key", api_style="responses"),
        output_dir=tmp_path,
    )
    runner = AgentRunner(config)

    result = await runner.run(TaskSpec(instruction="extract", url="data:text/html,<h1>Hello</h1>"))

    assert result.success
    assert result.final_message == "done"
    assert result.memory.extracted_data
    assert (Path(result.artifact_dir) / "result.json").exists()


@pytest.mark.asyncio
async def test_agent_loop_with_chat_completions_model(
    monkeypatch: pytest.MonkeyPatch,
    edge_executable: str,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("datacollector.models.clients.AsyncOpenAI", FakeOpenAI)
    config = RuntimeConfig(
        browser=BrowserConfig(headless=True, executable_path=edge_executable),
        model=ModelConfig(api_key="test-key", api_style="chat_completions"),
        output_dir=tmp_path,
    )
    runner = AgentRunner(config)

    result = await runner.run(TaskSpec(instruction="extract", url="data:text/html,<h1>Hello</h1>"))

    assert result.success
    assert result.final_message == "done"
    assert result.memory.extracted_data
    assert (Path(result.artifact_dir) / "result.json").exists()


@pytest.mark.asyncio
async def test_agent_stops_for_login_page_before_model_call(
    monkeypatch: pytest.MonkeyPatch,
    edge_executable: str,
    tmp_path: Path,
) -> None:
    def fail_if_model_is_created(*_: object) -> object:
        raise AssertionError("model should not be called when login is required")

    monkeypatch.setattr("datacollector.agent.runner.create_model_client", fail_if_model_is_created)
    config = RuntimeConfig(
        browser=BrowserConfig(headless=True, executable_path=edge_executable),
        output_dir=tmp_path,
    )
    runner = AgentRunner(config)
    html = "data:text/html;charset=utf-8," + quote(
        "<title>Login</title>"
        "<form><input name=email><input type=password><button>Login</button></form>"
    )

    result = await runner.run(TaskSpec(instruction="read private data", url=html))

    assert not result.success
    assert "登录" in result.final_message
    assert result.steps[0].status == "requires_human_intervention"


@pytest.mark.asyncio
async def test_chat_completions_model_accepts_dict_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "datacollector.models.clients.AsyncOpenAI",
        fake_openai_with_chat_response(
            {"choices": [{"message": {"role": "assistant", "content": "done"}}]}
        ),
    )
    client = ChatCompletionsModelClient(
        ModelConfig(api_key="test-key", api_style="chat_completions"),
        system_prompt="system",
    )

    turn = await client.turn("hello", tool_outputs=[], tools=[])

    assert turn.text == "done"


@pytest.mark.asyncio
async def test_chat_completions_model_reports_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "datacollector.models.clients.AsyncOpenAI",
        fake_openai_with_chat_response("<html>gateway</html>"),
    )
    client = ChatCompletionsModelClient(
        ModelConfig(
            api_key="test-key",
            api_style="chat_completions",
            base_url="http://localhost:8000/",
        ),
        system_prompt="system",
    )

    with pytest.raises(RuntimeError, match="/v1"):
        await client.turn("hello", tool_outputs=[], tools=[])
