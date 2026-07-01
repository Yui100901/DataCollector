from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from datacollector.agent.models import TaskSpec
from datacollector.agent.runner import AgentRunner
from datacollector.chat import ChatSession
from datacollector.config import RuntimeConfig
from datacollector.storage import SQLiteRunStore

app = typer.Typer(help="AI 驱动的 Playwright 浏览器自动化工具。")


def _load_config(config_file: Optional[Path]) -> RuntimeConfig:
    load_dotenv()
    return RuntimeConfig.from_toml(config_file) if config_file else RuntimeConfig.from_env()


def _apply_browser_options(
    config: RuntimeConfig,
    headless: Optional[bool],
    browser_channel: Optional[str] = None,
    browser_executable: Optional[Path] = None,
) -> None:
    if headless is not None:
        config.browser.headless = headless
    if browser_channel:
        config.browser.channel = browser_channel
    if browser_executable:
        config.browser.executable_path = str(browser_executable)


@app.command()
def chat(
    initial_message: Optional[str] = typer.Argument(None, help="可选的第一条消息。"),
    url: Optional[str] = typer.Option(None, "--url", help="第一轮对话开始时打开的 URL。"),
    headless: Optional[bool] = typer.Option(None, "--headless/--headed", help="是否使用无头浏览器。"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="会话和产物输出目录。"),
    browser_channel: Optional[str] = typer.Option(None, "--browser-channel", help="系统浏览器通道，例如 chrome 或 msedge。"),
    browser_executable: Optional[Path] = typer.Option(None, "--browser-executable", help="浏览器可执行文件路径。"),
    config_file: Optional[Path] = typer.Option(None, "--config", help="TOML 配置文件路径。"),
) -> None:
    """进入多轮交互式问答模式。"""

    config = _load_config(config_file)
    _apply_browser_options(config, headless, browser_channel, browser_executable)
    if output:
        config.output_dir = output

    session = ChatSession(config)

    async def chat_loop() -> None:
        typer.echo(f"DataCollector Chat 已启动，会话目录：{session.session_dir}")
        typer.echo("直接输入需求即可；输入 /help 查看命令；输入 /exit 退出。浏览器会在首次需要页面操作时启动。")

        async def handle(message: str, message_url: str | None = None) -> None:
            reply = await session.ask(message, url=message_url)
            typer.echo(f"\nAI: {reply.message}\n")
            if reply.exports:
                for item in reply.exports:
                    typer.echo(f"- {item.format}: {item.path}")

        try:
            first_url = url
            if initial_message:
                await handle(initial_message, first_url)
                first_url = None

            while True:
                message = typer.prompt("你")
                if message.strip().lower() in {"/exit", "exit", "quit", "q"}:
                    typer.echo(f"会话已保存：{session.session_dir}")
                    break
                await handle(message, first_url)
                first_url = None
        finally:
            await session.close()

    asyncio.run(chat_loop())


@app.command()
def run(
    instruction: str = typer.Argument(..., help="自然语言浏览器任务描述。"),
    url: Optional[str] = typer.Option(None, "--url", help="任务开始时打开的 URL。"),
    headless: Optional[bool] = typer.Option(None, "--headless/--headed", help="是否使用无头浏览器。"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="运行产物输出目录。"),
    schema_file: Optional[Path] = typer.Option(None, "--schema-file", help="期望输出 JSON schema 文件。"),
    browser_channel: Optional[str] = typer.Option(None, "--browser-channel", help="系统浏览器通道，例如 chrome 或 msedge。"),
    browser_executable: Optional[Path] = typer.Option(None, "--browser-executable", help="浏览器可执行文件路径。"),
    config_file: Optional[Path] = typer.Option(None, "--config", help="TOML 配置文件路径。"),
) -> None:
    """运行一次浏览器自动化任务。"""

    config = _load_config(config_file)
    _apply_browser_options(config, headless, browser_channel, browser_executable)
    if output:
        config.output_dir = output

    output_schema = None
    if schema_file:
        output_schema = json.loads(schema_file.read_text(encoding="utf-8"))

    task = TaskSpec(instruction=instruction, url=url, output_schema=output_schema)
    result = asyncio.run(AgentRunner(config).run(task))
    typer.echo(result.model_dump_json(indent=2))


@app.command("run-file")
def run_file(
    task_file: Path = typer.Argument(..., help="JSON 任务配置文件。"),
    headless: Optional[bool] = typer.Option(None, "--headless/--headed", help="是否使用无头浏览器。"),
    browser_executable: Optional[Path] = typer.Option(None, "--browser-executable", help="浏览器可执行文件路径。"),
    config_file: Optional[Path] = typer.Option(None, "--config", help="TOML 配置文件路径。"),
) -> None:
    """从 JSON 文件运行一个任务。"""

    config = _load_config(config_file)
    _apply_browser_options(config, headless, browser_executable=browser_executable)
    task = TaskSpec.model_validate_json(task_file.read_text(encoding="utf-8"))
    result = asyncio.run(AgentRunner(config).run(task))
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def config() -> None:
    """输出当前运行配置，敏感字段会被隐藏。"""

    load_dotenv()
    typer.echo(json.dumps(RuntimeConfig.from_env().to_safe_dict(), ensure_ascii=False, indent=2))


@app.command("list-runs")
def list_runs(
    limit: int = typer.Option(20, "--limit", "-n", help="返回最近运行数量。"),
    database: Optional[Path] = typer.Option(None, "--database", help="SQLite 数据库路径。"),
) -> None:
    """列出最近的运行记录。"""

    config = _load_config(None)
    database_path = database or config.database_path or (config.output_dir / "datacollector.sqlite3")
    rows = SQLiteRunStore(database_path).list_runs(limit=limit)
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))


@app.command("show-run")
def show_run(
    run_id: str = typer.Argument(..., help="运行 ID。"),
    database: Optional[Path] = typer.Option(None, "--database", help="SQLite 数据库路径。"),
) -> None:
    """查看指定运行记录。"""

    config = _load_config(None)
    database_path = database or config.database_path or (config.output_dir / "datacollector.sqlite3")
    row = SQLiteRunStore(database_path).get_run(run_id)
    if not row:
        raise typer.Exit(1)
    typer.echo(json.dumps(row, ensure_ascii=False, indent=2))
