from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


class ExportResult(BaseModel):
    format: str
    path: str
    rows: int


class DataArtifact(BaseModel):
    name: str = "dataset"
    rows: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @classmethod
    def from_extracted_data(cls, extracted_items: list[dict[str, Any]], name: str = "dataset") -> "DataArtifact":
        rows: list[dict[str, Any]] = []
        notes: list[str] = []

        for item in extracted_items:
            tool = item.get("tool", "")
            data = item.get("data", {})
            if not isinstance(data, dict):
                continue

            for link in data.get("links", []) or []:
                if isinstance(link, dict):
                    rows.append(
                        {
                            "type": "link",
                            "title": link.get("text", ""),
                            "url": link.get("href", ""),
                            "source_tool": tool,
                        }
                    )

            for media in data.get("media", []) or []:
                if isinstance(media, dict):
                    rows.append(
                        {
                            "type": media.get("tag", "media"),
                            "title": media.get("alt", ""),
                            "url": media.get("src", ""),
                            "source_tool": tool,
                        }
                    )

            for table in data.get("tables", []) or []:
                table_rows = table.get("rows", []) if isinstance(table, dict) else []
                if table_rows:
                    headers = [str(value) for value in table_rows[0]]
                    for raw_row in table_rows[1:]:
                        row = {headers[index]: value for index, value in enumerate(raw_row[: len(headers)])}
                        row["type"] = "table_row"
                        row["source_tool"] = tool
                        rows.append(row)

            for index, values in enumerate(data.get("lists", []) or []):
                if isinstance(values, list):
                    for value in values:
                        rows.append(
                            {
                                "type": "list_item",
                                "title": value,
                                "list_index": index,
                                "source_tool": tool,
                            }
                        )

            text = data.get("text")
            if isinstance(text, str) and text.strip():
                notes.append(text.strip())

        return cls(name=name, rows=DataCleaner.clean_rows(rows), notes=DataCleaner.clean_notes(notes))

    def export_markdown(self, path: Path) -> ExportResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = self.headers()
        lines = [f"# {self.name}", ""]
        if self.notes:
            lines.extend(["## Notes", ""])
            lines.extend(note[:2000] for note in self.notes[:5])
            lines.append("")
        if headers:
            lines.extend(["## Data", ""])
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in self.rows:
                lines.append("| " + " | ".join(self._md_cell(row.get(header, "")) for header in headers) + " |")
        path.write_text("\n".join(lines), encoding="utf-8")
        return ExportResult(format="markdown", path=str(path), rows=len(self.rows))

    def export_excel(self, path: Path) -> ExportResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Data"
        headers = self.headers()
        sheet.append(headers)
        for row in self.rows:
            sheet.append([row.get(header, "") for header in headers])

        if self.notes:
            notes = workbook.create_sheet("Notes")
            notes.append(["note"])
            for note in self.notes:
                notes.append([note])
        workbook.save(path)
        return ExportResult(format="excel", path=str(path), rows=len(self.rows))

    def export_pdf(self, path: Path) -> ExportResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(path), pagesize=A4)
        elements: list[Any] = [Paragraph(self.name, styles["Title"]), Spacer(1, 12)]

        for note in self.notes[:3]:
            elements.append(Paragraph(note[:1200], styles["BodyText"]))
            elements.append(Spacer(1, 8))

        headers = self.headers()
        if headers:
            preview_rows = [[str(row.get(header, ""))[:80] for header in headers] for row in self.rows[:30]]
            table = Table([headers] + preview_rows, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            elements.append(table)
        doc.build(elements)
        return ExportResult(format="pdf", path=str(path), rows=len(self.rows))

    def export_csv(self, path: Path) -> ExportResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = self.headers()
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(self.rows)
        return ExportResult(format="csv", path=str(path), rows=len(self.rows))

    def export_json(self, path: Path) -> ExportResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return ExportResult(format="json", path=str(path), rows=len(self.rows))

    def headers(self) -> list[str]:
        seen: list[str] = []
        for row in self.rows:
            for key in row.keys():
                if key not in seen:
                    seen.append(key)
        return seen

    @staticmethod
    def _md_cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()


class DataCleaner:
    @classmethod
    def clean_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cleaned: list[dict[str, Any]] = []
        seen = set()
        for row in rows:
            normalized = {
                str(key).strip(): cls.clean_value(value)
                for key, value in row.items()
                if value is not None and str(value).strip() != ""
            }
            if not normalized:
                continue
            signature = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
            if signature in seen:
                continue
            seen.add(signature)
            cleaned.append(normalized)
        return cleaned

    @classmethod
    def clean_notes(cls, notes: list[str]) -> list[str]:
        result: list[str] = []
        seen = set()
        for note in notes:
            cleaned = cls.clean_value(note)
            if cleaned and cleaned not in seen:
                result.append(cleaned)
                seen.add(cleaned)
        return result

    @staticmethod
    def clean_value(value: Any) -> str:
        text = str(value)
        text = re.sub(r"\s+", " ", text).strip()
        return text

