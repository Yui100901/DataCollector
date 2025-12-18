"""
Playwright 爬虫工具包
"""
from .browser_types import BrowserType
from .page_operator import PageOperator
from .page_manager import AsyncPageManager

__all__ = [
    'BrowserType',
    'PageOperator',
    'AsyncPageManager',
]

__version__ = '1.0.0'