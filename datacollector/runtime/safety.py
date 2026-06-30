from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel

from datacollector.config import AgentConfig


class SafetyResult(BaseModel):
    allowed: bool
    reason: str = ""
    requires_confirmation: bool = False
    category: str | None = None


class SafetyGuard:
    DANGEROUS_PATTERNS: dict[str, tuple[str, ...]] = {
        "payment": ("pay", "payment", "checkout", "购买", "支付", "付款", "结账"),
        "deletion": ("delete", "remove", "destroy", "删除", "移除", "注销"),
        "messaging": ("send", "submit", "publish", "发送", "提交", "发布"),
        "account_change": ("password", "email", "profile", "account", "密码", "邮箱", "账号", "账户"),
    }

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def check_navigation(self, url: str) -> SafetyResult:
        hostname = self._hostname(url)
        if not hostname:
            return SafetyResult(allowed=True)

        if any(self._domain_matches(hostname, domain) for domain in self.config.blocked_domains):
            return SafetyResult(allowed=False, reason=f"domain is blocked: {hostname}")

        if self.config.allowed_domains and not any(
            self._domain_matches(hostname, domain) for domain in self.config.allowed_domains
        ):
            return SafetyResult(allowed=False, reason=f"domain is not allowed: {hostname}")

        return SafetyResult(allowed=True)

    def check_action(self, tool_name: str, arguments: dict[str, object]) -> SafetyResult:
        if not self.config.require_confirmation_for_dangerous_actions:
            return SafetyResult(allowed=True)

        searchable = f"{tool_name} " + " ".join(str(value) for value in arguments.values())
        normalized = searchable.lower()
        for category, patterns in self.DANGEROUS_PATTERNS.items():
            if any(pattern.lower() in normalized for pattern in patterns):
                return SafetyResult(
                    allowed=False,
                    reason=f"dangerous action requires confirmation: {category}",
                    requires_confirmation=True,
                    category=category,
                )
        return SafetyResult(allowed=True)

    def mask(self, value: object) -> object:
        if not isinstance(value, str):
            return value
        if self._looks_secret(value):
            return "***"
        return value

    def mask_arguments(self, arguments: dict[str, object]) -> dict[str, object]:
        return {key: self.mask(value) for key, value in arguments.items()}

    @staticmethod
    def _hostname(url: str) -> str:
        return urlparse(url).hostname or ""

    @staticmethod
    def _domain_matches(hostname: str, domain: str) -> bool:
        normalized = domain.lower().lstrip(".")
        host = hostname.lower()
        return host == normalized or host.endswith(f".{normalized}")

    @staticmethod
    def _looks_secret(value: str) -> bool:
        if len(value) >= 24 and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
            return True
        return bool(re.search(r"(sk-|token|password|secret|api[_-]?key)", value, re.I))

