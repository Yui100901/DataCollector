from __future__ import annotations

import pytest

from datacollector.browser.runtime import BrowserRuntime
from datacollector.config import BrowserConfig


@pytest.mark.asyncio
async def test_browser_runtime_observes_fixture(edge_executable: str, fixture_html: str) -> None:
    async with BrowserRuntime(
        BrowserConfig(headless=True, executable_path=edge_executable)
    ) as runtime:
        await runtime.require_page().set_content(fixture_html)
        observation = await runtime.observe()

    assert observation.title == "DataCollector Fixture"
    assert observation.interactive_elements
    assert observation.links
    assert observation.tables[0].headers == ["Name", "Price"]

