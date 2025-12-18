"""
Playwright 爬虫工具包
封装异步页面管理和操作方法
用于操作获取复杂页面
"""
from base.browser_types import BrowserType
from .page_operator import PageOperator
from .page_manager import AsyncPageManager

__all__ = [
    'BrowserType',
    'PageOperator',
    'AsyncPageManager',
]

__version__ = '1.0.0'