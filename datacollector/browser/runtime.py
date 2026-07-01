from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, Field

from datacollector.config import BrowserConfig


class BrowserRuntimeError(RuntimeError):
    pass


class InteractiveElement(BaseModel):
    index: int
    tag: str
    role: str = ""
    type: str = ""
    text: str = ""
    selector_hint: str = ""
    href: str = ""
    visible: bool = True


class PageLink(BaseModel):
    text: str = ""
    href: str


class TableSummary(BaseModel):
    index: int
    headers: list[str] = Field(default_factory=list)
    row_count: int = 0
    sample_rows: list[list[str]] = Field(default_factory=list)


class HumanIntervention(BaseModel):
    category: str
    reason: str
    confidence: float = 1.0
    evidence: list[str] = Field(default_factory=list)


class PageObservation(BaseModel):
    url: str
    title: str
    text: str
    text_summary: str = ""
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)
    links: list[PageLink] = Field(default_factory=list)
    tables: list[TableSummary] = Field(default_factory=list)
    screenshot_path: str | None = None
    human_intervention: HumanIntervention | None = None


class BrowserRuntime:
    """Owns the Playwright lifecycle and provides compact page observations."""

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config = config or BrowserConfig()
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.contexts: dict[str, BrowserContext] = {}
        self.pages: dict[str, Page] = {}

    async def start(self) -> "BrowserRuntime":
        if self.browser:
            return self

        self.playwright = await async_playwright().start()
        launcher = getattr(self.playwright, self.config.browser.value)
        launch_options: dict[str, Any] = {"headless": self.config.headless}
        if self.config.channel:
            launch_options["channel"] = self.config.channel
        if self.config.executable_path:
            launch_options["executable_path"] = self.config.executable_path
        if self.config.downloads_path:
            launch_options["downloads_path"] = str(self.config.downloads_path)
        self.browser = await launcher.launch(**launch_options)
        self.context = await self.browser.new_context(**self._context_options())
        self.context.set_default_timeout(self.config.timeout_ms)
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.config.timeout_ms)
        self.contexts["default"] = self.context
        self.pages["default"] = self.page
        return self

    async def stop(self) -> None:
        try:
            if self.context:
                if self.config.auto_save_storage_state and self.config.storage_state:
                    await self.save_storage_state(self.config.storage_state)
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.contexts.clear()
            self.pages.clear()

    async def __aenter__(self) -> "BrowserRuntime":
        return await self.start()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.stop()

    def require_page(self) -> Page:
        if not self.page:
            raise BrowserRuntimeError("browser runtime has not been started")
        return self.page

    async def new_page(self) -> Page:
        if not self.context:
            raise BrowserRuntimeError("browser runtime has not been started")
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.config.timeout_ms)
        return self.page

    async def new_context(self, name: str, storage_state: Path | str | None = None) -> BrowserContext:
        if not self.browser:
            raise BrowserRuntimeError("browser runtime has not been started")
        options = self._context_options()
        if storage_state and Path(storage_state).exists():
            options["storage_state"] = str(storage_state)
        context = await self.browser.new_context(**options)
        context.set_default_timeout(self.config.timeout_ms)
        self.contexts[name] = context
        self.context = context
        page = await context.new_page()
        page.set_default_timeout(self.config.timeout_ms)
        self.page = page
        self.pages[name] = page
        return context

    async def switch_context(self, name: str) -> BrowserContext:
        context = self.contexts.get(name)
        if not context:
            raise BrowserRuntimeError(f"context does not exist: {name}")
        self.context = context
        self.page = self.pages.get(name) or await context.new_page()
        self.pages[name] = self.page
        return context

    async def new_named_page(self, name: str) -> Page:
        if not self.context:
            raise BrowserRuntimeError("browser runtime has not been started")
        page = await self.context.new_page()
        page.set_default_timeout(self.config.timeout_ms)
        self.pages[name] = page
        self.page = page
        return page

    def switch_page(self, name: str) -> Page:
        page = self.pages.get(name)
        if not page:
            raise BrowserRuntimeError(f"page does not exist: {name}")
        self.page = page
        return page

    async def start_tracing(self, screenshots: bool = True, snapshots: bool = True) -> None:
        if not self.context:
            raise BrowserRuntimeError("browser runtime has not been started")
        await self.context.tracing.start(screenshots=screenshots, snapshots=snapshots)

    async def stop_tracing(self, path: Path) -> None:
        if not self.context:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.context.tracing.stop(path=str(path))

    async def save_storage_state(self, path: Path) -> None:
        if not self.context:
            raise BrowserRuntimeError("browser runtime has not been started")
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.context.storage_state(path=str(path))

    async def observe(self, screenshot_path: Path | None = None) -> PageObservation:
        page = self.require_page()
        if screenshot_path:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=False)

        title = await page.title()
        text = await self._visible_text(page)
        text_summary = self._summarize_text(text)
        interactive_elements = await self._interactive_elements(page)
        links = await self._links(page)
        tables = await self._tables(page)
        human_intervention = await self._detect_human_intervention(
            page=page,
            title=title,
            text=text,
            interactive_elements=interactive_elements,
        )
        return PageObservation(
            url=page.url,
            title=title,
            text=text,
            text_summary=text_summary,
            interactive_elements=interactive_elements,
            links=links,
            tables=tables,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            human_intervention=human_intervention,
        )

    def _context_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "viewport": self.config.viewport,
            "extra_http_headers": self.config.headers,
            "accept_downloads": self.config.accept_downloads,
        }
        if self.config.user_agent:
            options["user_agent"] = self.config.user_agent
        if self.config.proxy:
            options["proxy"] = self.config.proxy.to_playwright()
        if self.config.locale:
            options["locale"] = self.config.locale
        if self.config.timezone_id:
            options["timezone_id"] = self.config.timezone_id
        if self.config.storage_state and self.config.storage_state.exists():
            options["storage_state"] = str(self.config.storage_state)
        return options

    async def _detect_human_intervention(
        self,
        page: Page,
        title: str,
        text: str,
        interactive_elements: list[InteractiveElement],
    ) -> HumanIntervention | None:
        signals = await self._page_auth_signals(page)
        combined_parts = [
            page.url,
            title,
            text[:4000],
            " ".join(element.text for element in interactive_elements[:30]),
            " ".join(signals.get("iframe_text", [])),
        ]
        combined = " ".join(combined_parts).lower()

        verification_keywords = {
            "captcha",
            "recaptcha",
            "hcaptcha",
            "turnstile",
            "cf-challenge",
            "cloudflare",
            "checking your browser",
            "verify you are human",
            "verify that you are human",
            "human verification",
            "unusual traffic",
            "security check",
            "访问前验证",
            "人机验证",
            "安全验证",
            "请完成验证",
            "验证您是真人",
            "验证你是真人",
            "滑块验证",
            "拖动滑块",
            "验证码",
        }
        verification_hits = sorted(keyword for keyword in verification_keywords if keyword in combined)
        if verification_hits or signals.get("verification_widgets", 0) > 0:
            evidence = verification_hits or ["verification widget"]
            return HumanIntervention(
                category="human_verification",
                reason="页面需要人机验证或安全验证，自动化应暂停等待人工处理。",
                evidence=evidence[:8],
            )

        parsed = urlparse(page.url)
        login_path_markers = {
            "login",
            "signin",
            "sign-in",
            "sso",
            "oauth",
            "auth",
            "account",
            "passport",
        }
        login_text_markers = {
            "login",
            "log in",
            "sign in",
            "password",
            "账号",
            "账户",
            "登录",
            "登入",
            "密码",
            "手机号",
            "邮箱",
        }
        path = (parsed.path or "").lower()
        login_path_hit = any(marker in path for marker in login_path_markers)
        login_text_hits = sorted(marker for marker in login_text_markers if marker in combined)
        password_inputs = int(signals.get("password_inputs", 0))

        if password_inputs > 0 or (login_path_hit and login_text_hits):
            evidence = [f"password_inputs={password_inputs}"] if password_inputs else []
            if login_path_hit:
                evidence.append(f"path={parsed.path}")
            evidence.extend(login_text_hits[:6])
            return HumanIntervention(
                category="login",
                reason="页面需要登录，自动化应暂停等待人工登录。",
                evidence=evidence[:8],
            )

        return None

    async def _page_auth_signals(self, page: Page) -> dict[str, Any]:
        script = """
        () => {
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0
              && style.visibility !== 'hidden'
              && style.display !== 'none';
          };
          const passwordInputs = Array.from(
            document.querySelectorAll('input[type="password"]')
          ).filter(visible).length;
          const iframeText = Array.from(document.querySelectorAll('iframe')).map((frame) => [
            frame.src || '',
            frame.title || '',
            frame.name || '',
            frame.id || '',
          ].join(' '));
          const verificationWidgets = Array.from(document.querySelectorAll(
            '[class*="captcha" i], [id*="captcha" i], [class*="recaptcha" i],'
            + ' [id*="recaptcha" i], [class*="hcaptcha" i], [id*="hcaptcha" i],'
            + ' [class*="turnstile" i], [id*="turnstile" i], [data-sitekey]'
          )).filter(visible).length;
          return { password_inputs: passwordInputs, iframe_text: iframeText, verification_widgets: verificationWidgets };
        }
        """
        try:
            value = await page.evaluate(script)
        except Exception:
            return {"password_inputs": 0, "iframe_text": [], "verification_widgets": 0}
        if not isinstance(value, dict):
            return {"password_inputs": 0, "iframe_text": [], "verification_widgets": 0}
        return value

    async def _visible_text(self, page: Page, limit: int = 6000) -> str:
        try:
            text = await page.locator("body").inner_text(timeout=2000)
        except Exception:
            text = ""
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    def _summarize_text(self, text: str, limit: int = 1200) -> str:
        sentences = re.split(r"(?<=[.!?。！？])\s+", text)
        summary = " ".join(sentence for sentence in sentences if sentence).strip()
        return summary[:limit]

    async def _interactive_elements(self, page: Page, limit: int = 80) -> list[InteractiveElement]:
        script = """
        (limit) => {
          const nodes = Array.from(document.querySelectorAll(
            'a,button,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]'
          )).filter((el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          });
          return nodes.slice(0, limit).map((el, index) => {
            const tag = el.tagName.toLowerCase();
            const role = el.getAttribute('role') || '';
            const type = el.getAttribute('type') || '';
            const name = el.getAttribute('aria-label')
              || el.getAttribute('placeholder')
              || el.innerText
              || el.value
              || el.getAttribute('name')
              || el.getAttribute('id')
              || '';
            const href = el.getAttribute('href') || '';
            const id = el.getAttribute('id');
            const testId = el.getAttribute('data-testid') || el.getAttribute('data-test');
            const selectorHint = testId ? `[data-testid="${testId}"]`
              : id ? `#${CSS.escape(id)}`
              : tag;
            return {
              index,
              tag,
              role,
              type,
              text: String(name).replace(/\\s+/g, ' ').trim().slice(0, 120),
              selector_hint: selectorHint,
              href,
              visible: true
            };
          });
        }
        """
        try:
            values = await page.evaluate(script, limit)
        except Exception:
            return []
        return [InteractiveElement.model_validate(value) for value in values[:limit]]

    async def _links(self, page: Page, limit: int = 50) -> list[PageLink]:
        script = """
        (limit) => Array.from(document.querySelectorAll('a[href]')).slice(0, limit).map((el) => ({
          text: (el.innerText || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
          href: el.href
        }))
        """
        try:
            values = await page.evaluate(script, limit)
        except Exception:
            return []
        return [PageLink.model_validate(value) for value in values if value.get("href")]

    async def _tables(self, page: Page, limit: int = 10) -> list[TableSummary]:
        script = """
        (limit) => Array.from(document.querySelectorAll('table')).slice(0, limit).map((table, index) => {
          const rows = Array.from(table.querySelectorAll('tr'));
          const headers = Array.from(table.querySelectorAll('th')).map((cell) =>
            cell.innerText.replace(/\\s+/g, ' ').trim()
          ).filter(Boolean);
          const sampleRows = rows.slice(0, 5).map((row) =>
            Array.from(row.querySelectorAll('th,td')).map((cell) =>
              cell.innerText.replace(/\\s+/g, ' ').trim()
            )
          ).filter((row) => row.length > 0);
          return { index, headers, row_count: rows.length, sample_rows: sampleRows };
        })
        """
        try:
            values = await page.evaluate(script, limit)
        except Exception:
            return []
        return [TableSummary.model_validate(value) for value in values]

    @staticmethod
    def domain_from_url(url: str) -> str:
        return urlparse(url).hostname or ""
