from __future__ import annotations

import asyncio

from datacollector import AgentRunner, BrowserConfig, RuntimeConfig, TaskSpec


async def main() -> None:
    config = RuntimeConfig.from_env()
    config.browser = BrowserConfig(headless=True)
    result = await AgentRunner(config).run(
        TaskSpec(
            instruction="打开 example.com 并总结页面内容。",
            url="https://example.com",
        )
    )
    print(result.final_message)


if __name__ == "__main__":
    asyncio.run(main())

