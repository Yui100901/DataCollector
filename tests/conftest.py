from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixture_html() -> str:
    path = Path(__file__).parent / "fixtures" / "simple.html"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def edge_executable() -> str:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    pytest.skip("No local Chrome or Edge executable is available.")

