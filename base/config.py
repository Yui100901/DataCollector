from typing import Optional, Dict
from urllib.parse import urlparse, urlunparse,quote


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
    ) -> None:
        if not server:
            raise ValueError("Proxy server 地址不能为空")

        if not server.startswith(('http://', 'https://', 'socks5://')):
            raise ValueError(f"无效的代理协议: {server}")

        self.server = server
        self.username = username
        self.password = password

    def to_url(self) -> str:
        """
        转换为 aiohttp 等需要的完整代理 URL
        有账号密码时拼接，没有时直接返回 server
        """
        parsed = urlparse(self.server)
        if self.username:
            auth = quote(self.username)
            if self.password:
                auth += f":{quote(self.password)}"
            netloc = f"{auth}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            result=str(urlunparse((
                parsed.scheme or '',
                netloc,
                parsed.path or '',
                parsed.params or '',
                parsed.query or '',
                parsed.fragment or ''
            )))
            return result
        else:
            return str(self.server)

    def __str__(self) -> str:
        return self.to_url()

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
    proxy: Optional[ProxyConfig]
    user_agent: Optional[str]
    headers: Dict[str, str]
    timeout: int

    def __init__(
            self,
            proxy: Optional[ProxyConfig] = None,
            user_agent: Optional[str] = None,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 30000
    ):
        self.proxy = proxy
        self.user_agent = user_agent
        self.headers = headers or {}
        self.timeout = timeout

