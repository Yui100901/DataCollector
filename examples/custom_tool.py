from __future__ import annotations

import asyncio
from pathlib import Path

from datacollector.browser import BrowserRuntime
from datacollector.config import AgentConfig, BrowserConfig
from datacollector.runtime import SafetyGuard
from datacollector.tools import BrowserToolRegistry, ToolResult


async def main() -> None:
    async with BrowserRuntime(BrowserConfig(headless=True)) as runtime:
        tools = BrowserToolRegistry(runtime, Path("runs/custom-tool"), SafetyGuard(AgentConfig()))

        async def current_length(_: dict[str, object]) -> ToolResult:
            page = runtime.require_page()
            text = await page.locator("body").inner_text()
            return ToolResult(
                success=True,
                tool="current_length",
                message="Read current page text length.",
                data={"length": len(text)},
            )

        tools.register_tool("current_length", "Return current page text length.", {}, current_length)


if __name__ == "__main__":
    asyncio.run(main())

