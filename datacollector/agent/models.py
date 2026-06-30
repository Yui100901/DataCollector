from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from datacollector.browser.runtime import PageObservation
from datacollector.observability.run_logger import ArtifactRecord


class TaskSpec(BaseModel):
    instruction: str
    url: str | None = None
    output_schema: dict[str, Any] | None = None


class TaskMemory(BaseModel):
    goal: str
    completed_actions: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    extracted_data: list[dict[str, Any]] = Field(default_factory=list)


class StepRecord(BaseModel):
    index: int
    observation: PageObservation | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_result: dict[str, Any] = Field(default_factory=dict)
    assistant_message: str = ""
    status: str = "pending"
    error: str | None = None


class RunResult(BaseModel):
    run_id: str
    success: bool
    task: TaskSpec
    started_at: datetime
    finished_at: datetime
    steps: list[StepRecord]
    memory: TaskMemory
    final_message: str
    artifact_dir: str
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
