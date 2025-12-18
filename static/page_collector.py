from base.config import BaseScraperConfig
import aiohttp
import asyncio


from typing import Optional, Dict

class PageCollectorConfig(BaseScraperConfig):
    def __init__(
            self,
            proxy: Optional[Dict[str, str]] = None,
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

    async def fetch(self, url: str, proxy: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> str:
        """异步爬取静态页面，支持为每个请求设置不同代理和 headers"""
        timeout = aiohttp.ClientTimeout(total=self.config.timeout / 1000)

        # 合并 headers
        merged_headers = dict(self.config.headers)
        if self.config.user_agent:
            merged_headers["User-Agent"] = self.config.user_agent
        if headers:
            merged_headers.update(headers)

        # 优先使用传入的代理，否则用配置里的默认代理
        proxy_url = proxy or (self.config.proxy if self.config.proxy else None)

        async with aiohttp.ClientSession(headers=merged_headers, timeout=timeout) as session:
            async with session.get(url, proxy=proxy_url) as response:
                response.raise_for_status()
                return await response.text()


async def main():
    config = PageCollectorConfig(
        user_agent="MyCustomAgent/1.0",
        headers={"Authorization": "Bearer TOKEN"},
        proxy={"server": "http://127.0.0.1:7890"},
        timeout=5000
    )
    collector = PageCollector(config)
    html = await collector.fetch("https://example.com")
    print(html[:200])  # 打印前200字符


if __name__ == "__main__":
    asyncio.run(main())