import pytest


@pytest.fixture(autouse=True)
def prevent_real_gemini_calls(monkeypatch):
    """Keep local Gemini credentials out of every automated test by default."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
