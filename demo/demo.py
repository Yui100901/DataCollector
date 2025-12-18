"""
爬虫工具使用示例
包含静态爬取和动态爬取的常见场景
"""
import asyncio
import logging
from typing import List, Dict
from bs4 import BeautifulSoup

from base import BrowserType, ProxyConfig
from page import AsyncPageManager, AsyncPageManagerConfig
from static import PageCollectorConfig, PageCollector

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def demo1():
    async with (AsyncPageManager(AsyncPageManagerConfig.default()) as manager):
        page =await manager.new_page("baidu",url="http://www.baidu.com")
        await page.chain()\
            .input("#chat-textarea", "hello")\
            .click('#chat-submit-button')\
            .wait_for_load()\
            .wait_for_timeout(10000)\
            .run()

async def main():
    await demo1()

if __name__ == "__main__":
    asyncio.run(main())