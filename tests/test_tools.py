from __future__ import annotations

from pathlib import Path

import pytest

from datacollector.browser.runtime import BrowserRuntime
from datacollector.config import AgentConfig, BrowserConfig
from datacollector.runtime.safety import SafetyGuard
from datacollector.tools.models import ToolResult
from datacollector.tools.playwright_tools import BrowserToolRegistry


@pytest.mark.asyncio
async def test_extract_structured_data(edge_executable: str, fixture_html: str, tmp_path: Path) -> None:
    async with BrowserRuntime(
        BrowserConfig(headless=True, executable_path=edge_executable)
    ) as runtime:
        await runtime.require_page().set_content(fixture_html)
        tools = BrowserToolRegistry(runtime, tmp_path, SafetyGuard(AgentConfig()))
        result = await tools.extract_structured_data({})

    assert result.success
    assert result.data["lists"] == [["One", "Two"]]
    assert result.data["tables"][0]["rows"][0] == ["Name", "Price"]
    assert result.data["links"][0]["href"] == "https://example.com/products/a"


@pytest.mark.asyncio
async def test_custom_tool_registration(edge_executable: str, tmp_path: Path) -> None:
    async with BrowserRuntime(
        BrowserConfig(headless=True, executable_path=edge_executable)
    ) as runtime:
        tools = BrowserToolRegistry(runtime, tmp_path, SafetyGuard(AgentConfig()))

        async def ping(_: dict[str, object]) -> ToolResult:
            return ToolResult(success=True, tool="ping", message="pong")

        tools.register_tool("ping", "Return pong.", {}, ping)
        result = await tools.execute("ping", {})

    assert result.success
    assert result.message == "pong"
    assert any(tool["name"] == "ping" for tool in tools.openai_tool_definitions)

