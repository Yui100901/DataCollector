from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from datacollector.config import ModelConfig


class ToolCall(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolOutput(BaseModel):
    call_id: str
    output: str


class ModelTurn(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ModelClient(ABC):
    def __init__(self, config: ModelConfig, system_prompt: str) -> None:
        if not config.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. For OpenAI-compatible local services, "
                "set it to any non-empty placeholder and configure OPENAI_BASE_URL."
            )
        self.config = config
        self.system_prompt = system_prompt
        self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)

    @abstractmethod
    async def turn(
        self,
        user_text: str,
        tool_outputs: list[ToolOutput],
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        raise NotImplementedError


class ResponsesModelClient(ModelClient):
    def __init__(self, config: ModelConfig, system_prompt: str) -> None:
        super().__init__(config, system_prompt)
        self.previous_response_id: str | None = None

    async def turn(
        self,
        user_text: str,
        tool_outputs: list[ToolOutput],
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        if tool_outputs:
            input_payload: list[dict[str, Any]] | str = [
                *[
                    {
                        "type": "function_call_output",
                        "call_id": output.call_id,
                        "output": output.output,
                    }
                    for output in tool_outputs
                ],
                {"role": "user", "content": user_text},
            ]
        else:
            input_payload = user_text

        response = await self.client.responses.create(
            model=self.config.model,
            instructions=self.system_prompt,
            input=input_payload,
            previous_response_id=self.previous_response_id,
            tools=tools,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )
        self.previous_response_id = response.id
        return ModelTurn(
            text=self._extract_text(response),
            tool_calls=self._extract_tool_calls(response),
        )

    def _extract_tool_calls(self, response: Any) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            calls.append(
                ToolCall(
                    call_id=getattr(item, "call_id", ""),
                    name=getattr(item, "name", ""),
                    arguments=self._loads_arguments(getattr(item, "arguments", "{}") or "{}"),
                )
            )
        return calls

    def _extract_text(self, response: Any) -> str:
        text = getattr(response, "output_text", None)
        if text:
            return str(text)

        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            content = getattr(item, "content", None)
            if not content:
                continue
            for part in content:
                if getattr(part, "type", None) in {"output_text", "text"}:
                    chunks.append(str(getattr(part, "text", "")))
        return "\n".join(chunk for chunk in chunks if chunk)

    @staticmethod
    def _loads_arguments(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


class ChatCompletionsModelClient(ModelClient):
    def __init__(self, config: ModelConfig, system_prompt: str) -> None:
        super().__init__(config, system_prompt)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    async def turn(
        self,
        user_text: str,
        tool_outputs: list[ToolOutput],
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        for output in tool_outputs:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": output.call_id,
                    "content": output.output,
                }
            )
        self.messages.append({"role": "user", "content": user_text})

        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=self.messages,
            tools=[self._to_chat_tool(tool) for tool in tools],
            temperature=self.config.temperature,
            max_tokens=self.config.max_output_tokens,
        )
        message = response.choices[0].message
        self.messages.append(self._assistant_message_for_history(message))
        return ModelTurn(
            text=str(getattr(message, "content", "") or ""),
            tool_calls=self._extract_tool_calls(message),
        )

    def _extract_tool_calls(self, message: Any) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for item in getattr(message, "tool_calls", None) or []:
            function = getattr(item, "function", None)
            if not function:
                continue
            calls.append(
                ToolCall(
                    call_id=getattr(item, "id", ""),
                    name=getattr(function, "name", ""),
                    arguments=self._loads_arguments(getattr(function, "arguments", "{}") or "{}"),
                )
            )
        return calls

    def _assistant_message_for_history(self, message: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": getattr(message, "content", None),
        }
        tool_calls = []
        for item in getattr(message, "tool_calls", None) or []:
            function = getattr(item, "function", None)
            if not function:
                continue
            tool_calls.append(
                {
                    "id": getattr(item, "id", ""),
                    "type": "function",
                    "function": {
                        "name": getattr(function, "name", ""),
                        "arguments": getattr(function, "arguments", "{}") or "{}",
                    },
                }
            )
        if tool_calls:
            payload["tool_calls"] = tool_calls
        return payload

    def _to_chat_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
            },
        }

    @staticmethod
    def _loads_arguments(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def create_model_client(config: ModelConfig, system_prompt: str) -> ModelClient:
    if config.api_style == "responses":
        return ResponsesModelClient(config, system_prompt)
    if config.api_style == "chat_completions":
        return ChatCompletionsModelClient(config, system_prompt)
    raise ValueError(f"unsupported model api_style: {config.api_style}")

