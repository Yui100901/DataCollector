from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from datacollector.agent.models import RunResult


class SQLiteRunStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def save_run(self, result: RunResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                insert or replace into runs (
                    run_id, success, instruction, url, started_at, finished_at,
                    final_message, artifact_dir, result_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    1 if result.success else 0,
                    result.task.instruction,
                    result.task.url,
                    result.started_at.isoformat(),
                    result.finished_at.isoformat(),
                    result.final_message,
                    result.artifact_dir,
                    result.model_dump_json(),
                ),
            )
            connection.execute("delete from steps where run_id = ?", (result.run_id,))
            connection.execute("delete from extracted_data where run_id = ?", (result.run_id,))
            connection.execute("delete from artifacts where run_id = ?", (result.run_id,))

            for step in result.steps:
                connection.execute(
                    """
                    insert into steps (
                        run_id, step_index, status, tool_name, current_url, error, step_json
                    ) values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.run_id,
                        step.index,
                        step.status,
                        step.tool_name,
                        step.observation.url if step.observation else "",
                        step.error,
                        step.model_dump_json(),
                    ),
                )

            for index, item in enumerate(result.memory.extracted_data):
                connection.execute(
                    """
                    insert into extracted_data (run_id, item_index, tool_name, data_json)
                    values (?, ?, ?, ?)
                    """,
                    (
                        result.run_id,
                        index,
                        item.get("tool", ""),
                        json.dumps(item.get("data", {}), ensure_ascii=False),
                    ),
                )

            for artifact in result.artifacts:
                connection.execute(
                    """
                    insert into artifacts (run_id, kind, path, description)
                    values (?, ?, ?, ?)
                    """,
                    (result.run_id, artifact.kind, artifact.path, artifact.description),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select result_json from runs where run_id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["result_json"])

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select run_id, success, instruction, url, started_at, finished_at,
                       final_message, artifact_dir
                from runs
                order by started_at desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists runs (
                    run_id text primary key,
                    success integer not null,
                    instruction text not null,
                    url text,
                    started_at text not null,
                    finished_at text not null,
                    final_message text not null,
                    artifact_dir text not null,
                    result_json text not null
                );

                create table if not exists steps (
                    id integer primary key autoincrement,
                    run_id text not null,
                    step_index integer not null,
                    status text not null,
                    tool_name text,
                    current_url text,
                    error text,
                    step_json text not null
                );

                create table if not exists extracted_data (
                    id integer primary key autoincrement,
                    run_id text not null,
                    item_index integer not null,
                    tool_name text,
                    data_json text not null
                );

                create table if not exists artifacts (
                    id integer primary key autoincrement,
                    run_id text not null,
                    kind text not null,
                    path text not null,
                    description text
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

