from typing import Optional, Dict

class ProxyConfig:
    """
    Playwright 代理配置类
    封装 server、username、password 三个参数
    """

    def __init__(
            self,
            server: str,
            username: Optional[str] = None,
            password: Optional[str] = None
    ):
        if not server:
            raise ValueError("Proxy server 地址不能为空")

        self.server = server
        self.username = username
        self.password = password

    def to_dict(self) -> Dict[str, str]:
        """
        转换为 Playwright 需要的字典格式
        """
        proxy_dict = {"server": self.server}
        if self.username:
            proxy_dict["username"] = self.username
        if self.password:
            proxy_dict["password"] = self.password
        return proxy_dict

    def __repr__(self):
        auth = f"{self.username}:{'***' if self.password else ''}@" if self.username else ""
        return f"<ProxyConfig {auth}{self.server}>"


class BaseScraperConfig:
    """共有的配置"""

    def __init__(
            self,
            proxy: Optional[ProxyConfig] = None,
            user_agent: Optional[str] = None,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 3000
    ):
        self.proxy = proxy
        self.user_agent = user_agent
        self.headers = headers or {}
        self.timeout = timeout

