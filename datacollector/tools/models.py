from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractedData(BaseModel):
    text: str = ""
    lists: list[list[str]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    media: list[dict[str, str]] = Field(default_factory=list)


class ToolResult(BaseModel):
    success: bool
    tool: str
    message: str = ""
    current_url: str = ""
    screenshot_path: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_code: str | None = None
    retryable: bool = False
    requires_confirmation: bool = False
    safety_category: str | None = None
