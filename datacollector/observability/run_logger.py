from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ArtifactRecord(BaseModel):
    kind: str
    path: str
    description: str = ""


class RunLogger:
    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.artifact_dir / "events.jsonl"
        self.tool_calls_path = self.artifact_dir / "tool-calls.jsonl"
        self.artifacts_path = self.artifact_dir / "artifacts.json"
        self._artifacts: list[ArtifactRecord] = []

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        self._write_json(self.artifact_dir / "metadata.json", metadata)

    def event(self, event: str, **payload: Any) -> None:
        self._append_jsonl(self.events_path, {"event": event, **payload})

    def tool_call(self, **payload: Any) -> None:
        self._append_jsonl(self.tool_calls_path, payload)

    def artifact(self, kind: str, path: str | Path, description: str = "") -> None:
        record = ArtifactRecord(kind=kind, path=str(path), description=description)
        self._artifacts.append(record)
        self._write_json(
            self.artifacts_path,
            [item.model_dump(mode="json") for item in self._artifacts],
        )

    @property
    def artifacts(self) -> list[ArtifactRecord]:
        return list(self._artifacts)

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        item = {
            "timestamp": datetime.now().isoformat(),
            **payload,
        }
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
