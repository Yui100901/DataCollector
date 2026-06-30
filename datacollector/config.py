from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator


class BrowserKind(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class ProxyConfig(BaseModel):
    server: str
    username: str | None = None
    password: str | None = None

    @field_validator("server")
    @classmethod
    def validate_server(cls, value: str) -> str:
        if not value:
            raise ValueError("proxy server cannot be empty")
        if not value.startswith(("http://", "https://", "socks5://")):
            raise ValueError(f"unsupported proxy protocol: {value}")
        return value

    def to_url(self) -> str:
        if not self.username:
            return self.server

        parsed = urlparse(self.server)
        auth = quote(self.username)
        if self.password:
            auth += f":{quote(self.password)}"

        netloc = f"{auth}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"

        return urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path or "",
                parsed.params or "",
                parsed.query or "",
                parsed.fragment or "",
            )
        )

    def to_playwright(self) -> dict[str, str]:
        payload = {"server": self.server}
        if self.username:
            payload["username"] = self.username
        if self.password:
            payload["password"] = self.password
        return payload


class BrowserConfig(BaseModel):
    browser: BrowserKind = BrowserKind.CHROMIUM
    headless: bool = False
    channel: str | None = None
    executable_path: str | None = None
    accept_downloads: bool = True
    downloads_path: Path | None = None
    storage_state: Path | None = None
    viewport: dict[str, int] = Field(default_factory=lambda: {"width": 1280, "height": 720})
    user_agent: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    proxy: ProxyConfig | None = None
    locale: str | None = None
    timezone_id: str | None = None
    timeout_ms: int = 30_000


class ModelConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    temperature: float = 0.2
    max_output_tokens: int = 1200
    api_key: str | None = None


class AgentConfig(BaseModel):
    max_steps: int = 12
    task_timeout_seconds: int = 120
    require_confirmation_for_dangerous_actions: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    trace_enabled: bool = True


class RuntimeConfig(BaseModel):
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    output_dir: Path = Path("runs")
    database_path: Path | None = None

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        headless = os.getenv("DATACOLLECTOR_HEADLESS", "false").lower() in {"1", "true", "yes"}
        allowed_domains = cls._split_env_list(os.getenv("DATACOLLECTOR_ALLOWED_DOMAINS", ""))
        blocked_domains = cls._split_env_list(os.getenv("DATACOLLECTOR_BLOCKED_DOMAINS", ""))
        return cls(
            browser=BrowserConfig(
                headless=headless,
                channel=os.getenv("DATACOLLECTOR_BROWSER_CHANNEL") or None,
                executable_path=os.getenv("DATACOLLECTOR_BROWSER_EXECUTABLE") or None,
                storage_state=Path(os.getenv("DATACOLLECTOR_STORAGE_STATE"))
                if os.getenv("DATACOLLECTOR_STORAGE_STATE")
                else None,
            ),
            model=ModelConfig(
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("DATACOLLECTOR_MODEL", "gpt-4.1-mini"),
                temperature=float(os.getenv("DATACOLLECTOR_TEMPERATURE", "0.2")),
                max_output_tokens=int(os.getenv("DATACOLLECTOR_MAX_OUTPUT_TOKENS", "1200")),
            ),
            agent=AgentConfig(
                max_steps=int(os.getenv("DATACOLLECTOR_MAX_STEPS", "12")),
                task_timeout_seconds=int(os.getenv("DATACOLLECTOR_TASK_TIMEOUT", "120")),
                allowed_domains=allowed_domains,
                blocked_domains=blocked_domains,
                trace_enabled=os.getenv("DATACOLLECTOR_TRACE", "true").lower()
                in {"1", "true", "yes"},
            ),
            output_dir=Path(os.getenv("DATACOLLECTOR_OUTPUT_DIR", "runs")),
            database_path=Path(os.getenv("DATACOLLECTOR_DATABASE"))
            if os.getenv("DATACOLLECTOR_DATABASE")
            else None,
        )

    @classmethod
    def from_toml(cls, path: Path) -> "RuntimeConfig":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        config = cls.from_env()

        browser = data.get("browser", {})
        for field in (
            "headless",
            "channel",
            "executable_path",
            "accept_downloads",
            "locale",
            "timezone_id",
            "timeout_ms",
        ):
            if field in browser:
                setattr(config.browser, field, browser[field])
        if "storage_state" in browser:
            config.browser.storage_state = Path(browser["storage_state"])
        if "downloads_path" in browser:
            config.browser.downloads_path = Path(browser["downloads_path"])

        model = data.get("model", {})
        for field in ("provider", "model", "temperature", "max_output_tokens"):
            if field in model:
                setattr(config.model, field, model[field])

        agent = data.get("agent", {})
        for field in (
            "max_steps",
            "task_timeout_seconds",
            "require_confirmation_for_dangerous_actions",
            "allowed_domains",
            "blocked_domains",
            "trace_enabled",
        ):
            if field in agent:
                setattr(config.agent, field, agent[field])

        runtime = data.get("runtime", {})
        if "output_dir" in runtime:
            config.output_dir = Path(runtime["output_dir"])
        if "database_path" in runtime:
            config.database_path = Path(runtime["database_path"])
        return config

    def to_safe_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        if data.get("model", {}).get("api_key"):
            data["model"]["api_key"] = "***"
        return data

    @staticmethod
    def _split_env_list(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]
