from typing import Optional, Literal, List, Dict, Any, Union, Callable
from playwright.async_api import Page, Locator, Error as PlaywrightError
import logging

class PageOperator:
    """页面操作封装类：即时操作"""

    def __init__(self, page: Page, logger_name: Optional[str] = None):
        self.page = page
        self.logger = logging.getLogger(logger_name or f"{__name__}.{id(self)}")

    # ===== 数据获取 =====
    async def get_text(self, selector: str, default: str = "") -> str:
        try:
            return await self.page.inner_text(selector)
        except PlaywrightError:
            return default

    async def get_attr(self, selector: str, attr: str, default: Optional[str] = None) -> Optional[str]:
        try:
            return await self.page.get_attribute(selector, attr)
        except PlaywrightError:
            return default

    async def get_html(self, selector: Optional[str] = None) -> str:
        try:
            return await (self.page.inner_html(selector) if selector else self.page.content())
        except PlaywrightError:
            return ""

    async def get_title(self) -> str:
        return await self.page.title()

    async def get_url(self) -> str:
        return self.page.url

    async def get_texts(self, selector: str) -> List[str]:
        locators = self.page.locator(selector)
        count = await locators.count()
        return [await locators.nth(i).text_content() or "" for i in range(count)]

    async def get_all(self, selector: str) -> List[Locator]:
        locator = self.page.locator(selector)
        count = await locator.count()
        return [locator.nth(i) for i in range(count)]

    async def count(self, selector: str) -> int:
        return await self.page.locator(selector).count()

    # ===== 高级操作 =====
    def locator(self, selector: str) -> Locator:
        return self.page.locator(selector)

    async def evaluate(self, script: str, arg: Optional[Any] = None) -> Any:
        return await self.page.evaluate(script, arg)

    async def screenshot(self, path: Optional[str] = None, full_page: bool = False) -> Union[bytes, None]:
        return await self.page.screenshot(path=path, full_page=full_page)

    async def pdf(self, path: str) -> None:
        await self.page.pdf(path=path)

    # ===== Builder入口 =====
    def chain(self) -> "PageOperatorChain":
        """返回一个链式操作对象"""
        return PageOperatorChain(self.page, self.logger)


class PageOperatorChain:
    """链式页面操作封装类：延迟执行，最后统一 run()"""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger
        self._tasks: List[Callable[[], Any]] = []

    # ===== 页面导航 =====
    def goto(self, url: str, wait_until: Literal["commit","domcontentloaded","load","networkidle"] = "networkidle") -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.goto(url, wait_until=wait_until))
        return self

    def reload(self, wait_until: Literal["commit","domcontentloaded","load","networkidle"] = "networkidle") -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.reload(wait_until=wait_until))
        return self

    def back(self) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.go_back())
        return self

    def forward(self) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.go_forward())
        return self

    def wait_for_load(self, state: Literal["domcontentloaded","load","networkidle"] = "networkidle") -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.wait_for_load_state(state))
        return self

    def wait_for_timeout(self, timeout: int) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.wait_for_timeout(timeout))
        return self

    # ===== 元素操作 =====
    def click(self, selector: str, timeout: Optional[int] = None, force: bool = False) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.click(selector, timeout=timeout, force=force))
        return self

    def batch_click(
            self,
            selectors: List[str],
            timeout: Optional[int] = None,
            force: bool = False
    ) -> "PageOperatorChain":
        for selector in selectors:
            self._tasks.append(lambda s=selector: self.page.click(s, timeout=timeout, force=force))
        return self

    def input(self, selector: str, text: str, delay: Optional[int] = None, clear: bool = True) -> "PageOperatorChain":
        if clear:
            self._tasks.append(lambda: self.page.fill(selector, text))
        else:
            self._tasks.append(lambda: self.page.type(selector, text, delay=delay))
        return self

    def batch_input(
            self,
            inputs: Union[Dict[str, str], List[Dict[str, Any]]],
            delay: Optional[int] = None,
            clear: bool = True
    ) -> "PageOperatorChain":
        # 如果传入的是 dict，转成统一的列表形式
        if isinstance(inputs, dict):
            inputs = [{"selector": k, "text": v} for k, v in inputs.items()]

        for item in inputs:
            selector, text = item["selector"], item["text"]
            if clear:
                self._tasks.append(lambda s=selector, t=text: self.page.fill(s, t))
            else:
                self._tasks.append(lambda s=selector, t=text: self.page.type(s, t, delay=delay))
        return self

    def select(self, selector: str, value: Union[str, List[str]]) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.select_option(selector, value))
        return self

    def check(self, selector: str) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.check(selector))
        return self

    def batch_check(self, selectors: List[str]) -> "PageOperatorChain":
        for selector in selectors:
            self._tasks.append(lambda s=selector: self.page.check(s))
        return self

    def uncheck(self, selector: str) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.uncheck(selector))
        return self

    def batch_uncheck(self, selectors: List[str]) -> "PageOperatorChain":
        for selector in selectors:
            self._tasks.append(lambda s=selector: self.page.uncheck(s))
        return self

    def hover(self, selector: str, timeout: Optional[int] = None) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.hover(selector, timeout=timeout))
        return self

    def wait_for_element(self, selector: str, timeout: Optional[int] = None, state: Literal["attached","detached","visible","hidden"] = "visible") -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.wait_for_selector(selector, timeout=timeout, state=state))
        return self

    def evaluate(self, script: str, arg: Optional[Any] = None) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.evaluate(script, arg))
        return self

    def screenshot(self, path: Optional[str] = None, full_page: bool = False) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.screenshot(path=path, full_page=full_page))
        return self

    def pdf(self, path: str) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.pdf(path=path))
        return self

    def scroll_to_bottom(self, step: int = 500, delay: int = 200) -> "PageOperatorChain":
        script = f"""
            async () => {{
                const distance = {step};
                const delay = {delay};
                while (window.scrollY + window.innerHeight < document.body.scrollHeight) {{
                    window.scrollBy(0, distance);
                    await new Promise(resolve => setTimeout(resolve, delay));
                }}
            }}
        """
        self._tasks.append(lambda: self.page.evaluate(script))
        return self

    def press(self, selector: str, key: str) -> "PageOperatorChain":
        self._tasks.append(lambda: self.page.press(selector, key))
        return self

    def batch_press(
            self,
            presses: Union[Dict[str, str], List[Dict[str, str]]],
    ) -> "PageOperatorChain":
        """
        presses: [{"selector": "#input1", "key": "Enter"}, {"selector": "#input2", "key": "Tab"}]
        """
        if isinstance(presses, dict):
            presses = [{"selector": k, "key": v} for k, v in presses.items()]

        for item in presses:
            selector, key = item["selector"], item["key"]
            self._tasks.append(lambda s=selector, k=key: self.page.press(s, k))
        return self

    # ===== 执行器 =====
    async def run(self,ignore_errors: bool = False) -> "PageOperatorChain":
        """按顺序执行所有收集的操作"""
        for task in self._tasks:
            try:
                await task()
            except PlaywrightError as e:
                self.logger.error(f"执行任务失败: {e}")
                if not ignore_errors:
                    raise
                continue
        self._tasks.clear()
        return self
