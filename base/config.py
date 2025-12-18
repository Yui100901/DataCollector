from typing import Optional, Dict


from typing import Optional, Dict

class BaseScraperConfig:
    """共有的配置"""

    def __init__(
            self,
            proxy: Optional[Dict[str, str]] = None,
            user_agent: Optional[str] = None,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 3000
    ):
        self.proxy = proxy
        self.user_agent = user_agent
        self.headers = headers or {}
        self.timeout = timeout

