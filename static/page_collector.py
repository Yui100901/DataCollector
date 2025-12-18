from base.config import BaseScraperConfig, ProxyConfig
import aiohttp
import asyncio


from typing import Optional, Dict

class PageCollectorConfig(BaseScraperConfig):
    def __init__(
            self,
            proxy: Optional[ProxyConfig] = None,
            user_agent: Optional[str] = None,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 3000
    ):
        # 调用父类构造函数，传递参数
        super().__init__(
            proxy=proxy,
            user_agent=user_agent,
            headers=headers,
            timeout=timeout
        )

class PageCollector:
    def __init__(self, config: PageCollectorConfig):
        self.config = config
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.config.timeout / 1000)
        self.session = aiohttp.ClientSession(headers=self.config.headers, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def fetch(self, url: str, proxy: Optional[ProxyConfig] = None,
                    headers: Optional[Dict[str, str]] = None) -> str:
        if not self.session:
            raise RuntimeError("ClientSession 未初始化,请用 async with PageCollector(...) 使用")

        merged_headers = dict(self.config.headers)
        if self.config.user_agent:
            merged_headers["User-Agent"] = self.config.user_agent
        if headers:
            merged_headers.update(headers)

        # 更准确的类型注解
        default_proxy: Optional[str] = (
            self.config.proxy.to_url() if isinstance(self.config.proxy, ProxyConfig) else None
        )
        proxy_url = proxy.to_url() if proxy else default_proxy

        async with self.session.get(url, proxy=proxy_url, headers=merged_headers) as response:
            response.raise_for_status()
            return await response.text()


