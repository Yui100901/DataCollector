from pathlib import Path

from datacollector.artifacts import DataArtifact


def test_data_artifact_exports_multiple_formats(tmp_path: Path) -> None:
    artifact = DataArtifact(
        name="Search Results",
        rows=[
            {"type": "link", "title": "Alpha", "url": "https://example.com/a"},
            {"type": "link", "title": "Alpha", "url": "https://example.com/a"},
            {"type": "link", "title": "Beta", "url": "https://example.com/b"},
        ],
        notes=["  hello   world  "],
    )
    artifact.rows = DataArtifact(name="Search Results", rows=artifact.rows).rows

    markdown = artifact.export_markdown(tmp_path / "result.md")
    excel = artifact.export_excel(tmp_path / "result.xlsx")
    pdf = artifact.export_pdf(tmp_path / "result.pdf")

    assert Path(markdown.path).exists()
    assert Path(excel.path).exists()
    assert Path(pdf.path).exists()


def test_data_artifact_from_extracted_data() -> None:
    artifact = DataArtifact.from_extracted_data(
        [
            {
                "tool": "extract_structured_data",
                "data": {
                    "links": [{"text": "Alpha", "href": "https://example.com/a"}],
                    "lists": [["One", "Two"]],
                    "tables": [{"rows": [["Name", "Price"], ["A", "10"]]}],
                    "text": "A note",
                },
            }
        ]
    )

    assert len(artifact.rows) == 4
    assert artifact.notes == ["A note"]

