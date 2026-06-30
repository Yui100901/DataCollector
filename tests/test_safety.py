from datacollector.config import AgentConfig
from datacollector.runtime.safety import SafetyGuard


def test_blocks_unlisted_domain_when_allowlist_is_set() -> None:
    guard = SafetyGuard(AgentConfig(allowed_domains=["example.com"]))

    result = guard.check_navigation("https://openai.com")

    assert not result.allowed
    assert "not allowed" in result.reason


def test_dangerous_action_requires_confirmation() -> None:
    guard = SafetyGuard(AgentConfig())

    result = guard.check_action("click", {"selector": "#delete"})

    assert not result.allowed
    assert result.requires_confirmation
    assert result.category == "deletion"

