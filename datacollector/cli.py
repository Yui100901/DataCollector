from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from datacollector.agent.models import TaskSpec
from datacollector.agent.runner import AgentRunner
from datacollector.config import RuntimeConfig
from datacollector.storage import SQLiteRunStore

app = typer.Typer(help="AI-driven browser automation powered by Playwright.")


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
    """运行一个 AI 浏览器自动化任务。"""

    load_dotenv()
    config = RuntimeConfig.from_toml(config_file) if config_file else RuntimeConfig.from_env()
    if headless is not None:
        config.browser.headless = headless
    if output:
        config.output_dir = output
    if browser_channel:
        config.browser.channel = browser_channel
    if browser_executable:
        config.browser.executable_path = str(browser_executable)

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

    load_dotenv()
    config = RuntimeConfig.from_toml(config_file) if config_file else RuntimeConfig.from_env()
    if headless is not None:
        config.browser.headless = headless
    if browser_executable:
        config.browser.executable_path = str(browser_executable)

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

    load_dotenv()
    config = RuntimeConfig.from_env()
    database_path = database or config.database_path or (config.output_dir / "datacollector.sqlite3")
    rows = SQLiteRunStore(database_path).list_runs(limit=limit)
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))


@app.command("show-run")
def show_run(
    run_id: str = typer.Argument(..., help="运行 ID。"),
    database: Optional[Path] = typer.Option(None, "--database", help="SQLite 数据库路径。"),
) -> None:
    """查看指定运行记录。"""

    load_dotenv()
    config = RuntimeConfig.from_env()
    database_path = database or config.database_path or (config.output_dir / "datacollector.sqlite3")
    row = SQLiteRunStore(database_path).get_run(run_id)
    if not row:
        raise typer.Exit(1)
    typer.echo(json.dumps(row, ensure_ascii=False, indent=2))
