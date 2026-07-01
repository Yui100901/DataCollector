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


@pytest.mark.asyncio
async def test_browser_runtime_detects_login_page(edge_executable: str) -> None:
    async with BrowserRuntime(
        BrowserConfig(headless=True, executable_path=edge_executable)
    ) as runtime:
        await runtime.require_page().set_content(
            """
            <title>Sign in</title>
            <form>
              <input name="email">
              <input type="password" name="password">
              <button>Sign in</button>
            </form>
            """
        )
        observation = await runtime.observe()

    assert observation.human_intervention is not None
    assert observation.human_intervention.category == "login"


@pytest.mark.asyncio
async def test_browser_runtime_detects_human_verification(edge_executable: str) -> None:
    async with BrowserRuntime(
        BrowserConfig(headless=True, executable_path=edge_executable)
    ) as runtime:
        await runtime.require_page().set_content(
            """
            <title>Security check</title>
            <main>Please verify you are human before continuing.</main>
            """
        )
        observation = await runtime.observe()

    assert observation.human_intervention is not None
    assert observation.human_intervention.category == "human_verification"
