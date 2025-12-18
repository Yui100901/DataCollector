"""
页面管理器
"""
from typing import Optional, Dict
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext
import logging

from .browser_types import BrowserType
from .config import BaseScraperConfig
from .page_operator import PageOperator



class AsyncPageManager:
    """异步页面管理器，支持多上下文和多页面管理"""

    def __init__(
            self,
            headless: bool = True,
            browser: BrowserType = BrowserType.CHROMIUM,
            timeout: int = 30000,
            default_context_name: str = "default",
            viewport: Optional[Dict[str, int]] = None,
            user_agent: Optional[str] = None,
            proxy: Optional[Dict[str, str]] = None,
            default_headers: Optional[Dict[str, str]] = None,
            logger_name: Optional[str] = None
    ):
        self.headless = headless
        self.browser_type = browser.value
        self.timeout = timeout
        self.default_context_name = default_context_name
        self.viewport = viewport or {"width": 1280, "height": 720}
        self.user_agent = user_agent
        self.proxy = proxy
        self.default_headers = default_headers or {}

        self.logger = logging.getLogger(logger_name or __name__)

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.contexts: Dict[str, BrowserContext] = {}
        self.pages: Dict[str, Dict[str, PageOperator]] = {}
        self._started = False

    def _resolve_context_name(self, context_name: Optional[str]) -> str:
        """解析上下文名称"""
        return context_name or self.default_context_name

    async def start(self):
        """启动浏览器"""
        if self._started:
            self.logger.warning("浏览器已启动")
            return

        try:
            self.logger.info(f"正在启动 {self.browser_type} 浏览器...")
            self.playwright = await async_playwright().start()
            self.browser = await getattr(self.playwright, self.browser_type).launch(
                headless=self.headless
            )

            # 创建默认上下文
            await self.new_context(self.default_context_name)
            self._started = True
            self.logger.info(f"浏览器启动成功: {self.browser_type}")
        except Exception as e:
            self.logger.error(f"启动浏览器失败: {e}", exc_info=True)
            raise

    async def new_context(
            self,
            name: str,
            viewport: Optional[Dict[str, int]] = None,
            user_agent: Optional[str] = None,
            locale: Optional[str] = None,
            timezone_id: Optional[str] = None,
            proxy: Optional[Dict[str, str]] = None,
            extra_http_headers: Optional[Dict[str, str]] = None
    ) -> BrowserContext:
        context_options = {
            "viewport": viewport or self.viewport,
            "user_agent": user_agent or self.user_agent,
            "extra_http_headers": extra_http_headers or self.default_headers,
        }
        if locale:
            context_options["locale"] = locale
        if timezone_id:
            context_options["timezone_id"] = timezone_id
        if proxy or self.proxy:   # 优先使用传入的代理，否则用默认代理
            context_options["proxy"] = proxy or self.proxy

        context = await self.browser.new_context(**context_options)
        context.set_default_timeout(self.timeout)
        self.contexts[name] = context
        self.pages[name] = {}
        return context

    async def new_page(
            self,
            page_name: str,
            context_name: Optional[str] = None,
            url: Optional[str] = None
    ) -> PageOperator:
        """创建新页面"""
        context_name = self._resolve_context_name(context_name)
        context = self.contexts.get(context_name)

        if not context:
            raise ValueError(f"上下文不存在: {context_name}")

        if page_name in self.pages[context_name]:
            self.logger.warning(f"页面 {page_name} 已存在于上下文 {context_name}，返回现有页面")
            return self.pages[context_name][page_name]

        self.logger.info(f"创建页面: {page_name} (上下文: {context_name})")
        page = await context.new_page()
        page.set_default_timeout(self.timeout)

        # 为每个页面创建独立的 logger
        page_logger_name = f"{self.logger.name}.page.{context_name}.{page_name}"
        operator = PageOperator(page, logger_name=page_logger_name)
        self.pages[context_name][page_name] = operator

        if url:
            await operator.chain().goto(url).run()

        self.logger.info(f"页面创建成功: {page_name}")
        return operator

    def get_page(
            self,
            page_name: str,
            context_name: Optional[str] = None
    ) -> Optional[PageOperator]:
        """获取指定页面"""
        context_name = self._resolve_context_name(context_name)
        page = self.pages.get(context_name, {}).get(page_name)
        if page:
            self.logger.debug(f"获取页面: {page_name} (上下文: {context_name})")
        else:
            self.logger.debug(f"页面不存在: {page_name} (上下文: {context_name})")
        return page

    async def close_page(self, page_name: str, context_name: Optional[str] = None):
        """关闭指定页面"""
        context_name = self._resolve_context_name(context_name)
        operator = self.get_page(page_name, context_name)

        if operator:
            self.logger.info(f"关闭页面: {page_name} (上下文: {context_name})")
            await operator.page.close()
            del self.pages[context_name][page_name]
            self.logger.info(f"页面已关闭: {page_name}")
        else:
            self.logger.warning(f"页面不存在，无法关闭: {page_name}")

    async def close_context(self, context_name: str):
        """关闭指定上下文及其所有页面"""
        if context_name not in self.contexts:
            self.logger.warning(f"上下文不存在: {context_name}")
            return

        page_count = len(self.pages.get(context_name, {}))
        self.logger.info(f"关闭上下文: {context_name} ({page_count} 个页面)")

        await self.contexts[context_name].close()
        del self.contexts[context_name]
        del self.pages[context_name]

        self.logger.info(f"上下文已关闭: {context_name}")

    async def quit(self):
        """关闭浏览器并清理资源"""
        if not self._started:
            self.logger.debug("浏览器未启动，无需关闭")
            return

        try:
            total_contexts = len(self.contexts)
            total_pages = sum(len(pages) for pages in self.pages.values())

            self.logger.info(f"正在关闭浏览器 ({total_contexts} 个上下文, {total_pages} 个页面)...")

            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()

            self._started = False
            self.logger.info("浏览器已关闭")
        except Exception as e:
            self.logger.error(f"关闭浏览器失败: {e}", exc_info=True)

    @asynccontextmanager
    async def managed_page(
            self,
            page_name: str,
            url: Optional[str] = None,
            context_name: Optional[str] = None
    ):
        """上下文管理器:自动管理页面生命周期"""
        self.logger.debug(f"进入 managed_page: {page_name}")
        operator = await self.new_page(page_name, context_name, url)
        try:
            yield operator
        finally:
            await self.close_page(page_name, context_name)
            self.logger.debug(f"退出 managed_page: {page_name}")

    async def __aenter__(self):
        """支持 async with 语法"""
        self.logger.debug("进入 AsyncPageManager 上下文")
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """自动清理资源"""
        self.logger.debug("退出 AsyncPageManager 上下文")
        await self.quit()