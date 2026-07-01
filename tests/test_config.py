from pathlib import Path

from datacollector.config import RuntimeConfig


def test_model_base_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "local-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("DATACOLLECTOR_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("DATACOLLECTOR_MODEL_API_STYLE", "chat_completions")

    config = RuntimeConfig.from_env()

    assert config.model.api_key == "local-key"
    assert config.model.base_url == "http://localhost:11434/v1"
    assert config.model.model == "qwen2.5:7b"
    assert config.model.api_style == "chat_completions"


def test_model_base_url_from_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    path = tmp_path / "config.toml"
    path.write_text(
        """
        [model]
        api_key = "local-key"
        base_url = "http://localhost:8000/v1"
        model = "local-model"
        api_style = "chat_completions"
        """,
        encoding="utf-8",
    )

    config = RuntimeConfig.from_toml(path)

    assert config.model.api_key == "local-key"
    assert config.model.base_url == "http://localhost:8000/v1"
    assert config.model.model == "local-model"
    assert config.model.api_style == "chat_completions"
