from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from datacollector.browser.runtime import BrowserRuntime
from datacollector.runtime.safety import SafetyGuard
from datacollector.tools.models import ExtractedData, ToolResult


class BrowserToolRegistry:
    """Typed Playwright tools exposed to the AI agent."""

    def __init__(self, runtime: BrowserRuntime, artifact_dir: Path, safety: SafetyGuard) -> None:
        self.runtime = runtime
        self.artifact_dir = artifact_dir
        self.safety = safety
        self._custom_tool_definitions: list[dict[str, Any]] = []
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[ToolResult]]] = {
            "goto": self.goto,
            "click": self.click,
            "fill": self.fill,
            "press": self.press,
            "wait": self.wait,
            "wait_for_selector": self.wait_for_selector,
            "scroll": self.scroll,
            "screenshot": self.screenshot,
            "get_page_text": self.get_page_text,
            "get_page_url": self.get_page_url,
            "get_page_title": self.get_page_title,
            "extract_links": self.extract_links,
            "extract_media": self.extract_media,
            "extract_tables": self.extract_tables,
            "extract_lists": self.extract_lists,
            "extract_structured_data": self.extract_structured_data,
            "download_by_click": self.download_by_click,
            "upload_file": self.upload_file,
            "save_pdf": self.save_pdf,
            "save_storage_state": self.save_storage_state,
            "new_page": self.new_page,
            "switch_page": self.switch_page,
            "new_context": self.new_context,
            "switch_context": self.switch_context,
        }

    @property
    def openai_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            self._function_tool("goto", "Navigate the current page to a URL.", {"url": "string"}),
            self._function_tool(
                "click",
                "Click an element by CSS selector or Playwright selector.",
                {"selector": "string"},
            ),
            self._function_tool(
                "fill",
                "Fill an input-like element with text.",
                {"selector": "string", "text": "string"},
            ),
            self._function_tool(
                "press",
                "Press a keyboard key on an element.",
                {"selector": "string", "key": "string"},
            ),
            self._function_tool(
                "wait",
                "Wait for a number of milliseconds.",
                {"milliseconds": "integer"},
            ),
            self._function_tool(
                "wait_for_selector",
                "Wait for an element to appear.",
                {"selector": "string"},
            ),
            self._function_tool(
                "scroll",
                "Scroll the page vertically.",
                {"delta_y": "integer"},
            ),
            self._function_tool("screenshot", "Capture a screenshot.", {}),
            self._function_tool("get_page_text", "Read visible page text.", {}),
            self._function_tool("get_page_url", "Read the current page URL.", {}),
            self._function_tool("get_page_title", "Read the current page title.", {}),
            self._function_tool("extract_links", "Extract links from the current page.", {}),
            self._function_tool("extract_media", "Extract image, video, audio, and source URLs.", {}),
            self._function_tool("extract_tables", "Extract HTML tables as row data.", {}),
            self._function_tool("extract_lists", "Extract visible ordered and unordered lists.", {}),
            self._function_tool(
                "extract_structured_data",
                "Extract page text, lists, tables, links, and media in one structured payload.",
                {},
            ),
            self._function_tool(
                "download_by_click",
                "Click an element that triggers a download and save the file.",
                {"selector": "string"},
            ),
            self._function_tool(
                "upload_file",
                "Upload a local file through a file input selector.",
                {"selector": "string", "path": "string"},
            ),
            self._function_tool("save_pdf", "Save the current page as a PDF.", {"path": "string"}),
            self._function_tool(
                "save_storage_state",
                "Save cookies and local storage state to a JSON file.",
                {"path": "string"},
            ),
            self._function_tool("new_page", "Create and switch to a named page.", {"name": "string"}),
            self._function_tool("switch_page", "Switch to an existing named page.", {"name": "string"}),
            self._function_tool(
                "new_context",
                "Create and switch to a named browser context.",
                {"name": "string"},
            ),
            self._function_tool(
                "switch_context",
                "Switch to an existing named browser context.",
                {"name": "string"},
            ),
        ] + self._custom_tool_definitions

    def register_tool(
        self,
        name: str,
        description: str,
        properties: dict[str, str],
        handler: Callable[[dict[str, Any]], Awaitable[ToolResult]],
    ) -> None:
        self._handlers[name] = handler
        self._custom_tool_definitions.append(self._function_tool(name, description, properties))

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self._handlers.get(name)
        if not handler:
            return ToolResult(success=False, tool=name, message=f"unknown tool: {name}")
        safety_result = self._check_safety(name, arguments)
        if not safety_result.allowed:
            page = self.runtime.page
            return ToolResult(
                success=False,
                tool=name,
                message=safety_result.reason,
                current_url=page.url if page else "",
                error_type="safety",
                error_code="confirmation_required"
                if safety_result.requires_confirmation
                else "blocked_by_policy",
                retryable=False,
                requires_confirmation=safety_result.requires_confirmation,
                safety_category=safety_result.category,
            )
        try:
            return await handler(arguments)
        except Exception as exc:
            page = self.runtime.page
            return ToolResult(
                success=False,
                tool=name,
                message=f"{type(exc).__name__}: {exc}",
                current_url=page.url if page else "",
                error_type=type(exc).__name__,
                error_code="tool_execution_failed",
                retryable=True,
            )

    async def goto(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        url = str(args["url"])
        response = await page.goto(url, wait_until="domcontentloaded")
        return ToolResult(
            success=True,
            tool="goto",
            current_url=page.url,
            message=f"navigated to {page.url}",
            data={"status": response.status if response else None},
        )

    async def click(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        selector = str(args["selector"])
        await page.click(selector)
        return ToolResult(success=True, tool="click", current_url=page.url, message=f"clicked {selector}")

    async def fill(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        selector = str(args["selector"])
        text = str(args["text"])
        await page.fill(selector, text)
        return ToolResult(success=True, tool="fill", current_url=page.url, message=f"filled {selector}")

    async def press(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        selector = str(args["selector"])
        key = str(args["key"])
        await page.press(selector, key)
        return ToolResult(
            success=True,
            tool="press",
            current_url=page.url,
            message=f"pressed {key} on {selector}",
        )

    async def wait(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        milliseconds = int(args.get("milliseconds", 1000))
        await page.wait_for_timeout(milliseconds)
        return ToolResult(success=True, tool="wait", current_url=page.url, message=f"waited {milliseconds}ms")

    async def wait_for_selector(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        selector = str(args["selector"])
        await page.wait_for_selector(selector, state="visible")
        return ToolResult(
            success=True,
            tool="wait_for_selector",
            current_url=page.url,
            message=f"selector visible: {selector}",
        )

    async def scroll(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        delta_y = int(args.get("delta_y", 800))
        await page.mouse.wheel(0, delta_y)
        await asyncio.sleep(0.2)
        return ToolResult(success=True, tool="scroll", current_url=page.url, message=f"scrolled {delta_y}px")

    async def screenshot(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        index = len(list(self.artifact_dir.glob("screenshot-*.png"))) + 1
        path = self.artifact_dir / f"screenshot-{index:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=bool(args.get("full_page", False)))
        return ToolResult(
            success=True,
            tool="screenshot",
            current_url=page.url,
            screenshot_path=str(path),
            message=f"screenshot saved to {path}",
        )

    async def get_page_text(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        text = await page.locator("body").inner_text(timeout=2000)
        return ToolResult(
            success=True,
            tool="get_page_text",
            current_url=page.url,
            data={"text": text[:8000]},
        )

    async def get_page_url(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        return ToolResult(success=True, tool="get_page_url", current_url=page.url, data={"url": page.url})

    async def get_page_title(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        title = await page.title()
        return ToolResult(success=True, tool="get_page_title", current_url=page.url, data={"title": title})

    async def extract_links(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        links = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a[href]')).map((el) => ({
              text: (el.innerText || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim(),
              href: el.href
            })).filter((item) => item.href)
            """
        )
        return ToolResult(success=True, tool="extract_links", current_url=page.url, data={"links": links})

    async def extract_media(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        media = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('img,video,audio,source')).map((el) => ({
              tag: el.tagName.toLowerCase(),
              src: el.currentSrc || el.src || el.getAttribute('src') || '',
              alt: el.getAttribute('alt') || '',
              type: el.getAttribute('type') || ''
            })).filter((item) => item.src)
            """
        )
        return ToolResult(success=True, tool="extract_media", current_url=page.url, data={"media": media})

    async def extract_tables(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        tables = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('table')).map((table, index) => {
              const rows = Array.from(table.querySelectorAll('tr')).map((row) =>
                Array.from(row.querySelectorAll('th,td')).map((cell) =>
                  cell.innerText.replace(/\\s+/g, ' ').trim()
                )
              ).filter((row) => row.length > 0);
              return { index, rows };
            })
            """
        )
        return ToolResult(success=True, tool="extract_tables", current_url=page.url, data={"tables": tables})

    async def extract_lists(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        lists = await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('ul,ol')).map((list) =>
              Array.from(list.querySelectorAll(':scope > li')).map((item) =>
                item.innerText.replace(/\\s+/g, ' ').trim()
              ).filter(Boolean)
            ).filter((items) => items.length > 0)
            """
        )
        return ToolResult(success=True, tool="extract_lists", current_url=page.url, data={"lists": lists})

    async def extract_structured_data(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        text = re.sub(r"\s+", " ", await page.locator("body").inner_text(timeout=2000)).strip()
        links_result = await self.extract_links({})
        media_result = await self.extract_media({})
        tables_result = await self.extract_tables({})
        lists_result = await self.extract_lists({})
        payload = ExtractedData(
            text=text[:12000],
            lists=lists_result.data.get("lists", []),
            tables=tables_result.data.get("tables", []),
            links=links_result.data.get("links", []),
            media=media_result.data.get("media", []),
        )
        return ToolResult(
            success=True,
            tool="extract_structured_data",
            current_url=page.url,
            data=payload.model_dump(mode="json"),
        )

    async def download_by_click(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        selector = str(args["selector"])
        async with page.expect_download() as download_info:
            await page.click(selector)
        download = await download_info.value
        suggested = download.suggested_filename
        path = self.artifact_dir / "downloads" / suggested
        path.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(path))
        return ToolResult(
            success=True,
            tool="download_by_click",
            current_url=page.url,
            message=f"download saved to {path}",
            data={"path": str(path), "suggested_filename": suggested},
        )

    async def upload_file(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        selector = str(args["selector"])
        path = Path(str(args["path"]))
        await page.set_input_files(selector, str(path))
        return ToolResult(
            success=True,
            tool="upload_file",
            current_url=page.url,
            message=f"uploaded file to {selector}",
            data={"path": str(path)},
        )

    async def save_pdf(self, args: dict[str, Any]) -> ToolResult:
        page = self.runtime.require_page()
        requested = Path(str(args["path"]))
        path = requested if requested.is_absolute() else self.artifact_dir / requested
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.pdf(path=str(path))
        return ToolResult(
            success=True,
            tool="save_pdf",
            current_url=page.url,
            message=f"pdf saved to {path}",
            data={"path": str(path)},
        )

    async def save_storage_state(self, args: dict[str, Any]) -> ToolResult:
        requested = Path(str(args["path"]))
        path = requested if requested.is_absolute() else self.artifact_dir / requested
        await self.runtime.save_storage_state(path)
        page = self.runtime.require_page()
        return ToolResult(
            success=True,
            tool="save_storage_state",
            current_url=page.url,
            message=f"storage state saved to {path}",
            data={"path": str(path)},
        )

    async def new_page(self, args: dict[str, Any]) -> ToolResult:
        name = str(args["name"])
        page = await self.runtime.new_named_page(name)
        return ToolResult(
            success=True,
            tool="new_page",
            current_url=page.url,
            message=f"created page: {name}",
            data={"name": name},
        )

    async def switch_page(self, args: dict[str, Any]) -> ToolResult:
        name = str(args["name"])
        page = self.runtime.switch_page(name)
        return ToolResult(
            success=True,
            tool="switch_page",
            current_url=page.url,
            message=f"switched to page: {name}",
            data={"name": name},
        )

    async def new_context(self, args: dict[str, Any]) -> ToolResult:
        name = str(args["name"])
        await self.runtime.new_context(name)
        page = self.runtime.require_page()
        return ToolResult(
            success=True,
            tool="new_context",
            current_url=page.url,
            message=f"created context: {name}",
            data={"name": name},
        )

    async def switch_context(self, args: dict[str, Any]) -> ToolResult:
        name = str(args["name"])
        await self.runtime.switch_context(name)
        page = self.runtime.require_page()
        return ToolResult(
            success=True,
            tool="switch_context",
            current_url=page.url,
            message=f"switched to context: {name}",
            data={"name": name},
        )

    def _function_tool(
        self,
        name: str,
        description: str,
        properties: dict[str, str],
    ) -> dict[str, Any]:
        required = list(properties.keys())
        schema_properties = {
            key: {"type": value, "description": key.replace("_", " ")}
            for key, value in properties.items()
        }
        return {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": schema_properties,
                "required": required,
                "additionalProperties": False,
            },
        }

    def _check_safety(self, name: str, arguments: dict[str, Any]):
        if name == "goto":
            return self.safety.check_navigation(str(arguments.get("url", "")))
        if name in {"click", "fill", "press"}:
            return self.safety.check_action(name, arguments)
        return self.safety.check_action(name, arguments)
