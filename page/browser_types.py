"""
浏览器类型枚举
"""
from enum import Enum


class BrowserType(Enum):
    """支持的浏览器类型"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"
