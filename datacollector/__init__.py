"""AI-driven browser automation runtime powered by Playwright."""

from datacollector.agent.models import RunResult, TaskMemory, TaskSpec
from datacollector.agent.runner import AgentRunner
from datacollector.browser.runtime import BrowserRuntime
from datacollector.config import AgentConfig, BrowserConfig, ModelConfig, RuntimeConfig

__all__ = [
    "AgentConfig",
    "AgentRunner",
    "BrowserConfig",
    "BrowserRuntime",
    "ModelConfig",
    "RunResult",
    "RuntimeConfig",
    "TaskMemory",
    "TaskSpec",
]

__version__ = "0.1.0"
