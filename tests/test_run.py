import uvicorn

import run


def test_main_starts_uvicorn_with_local_defaults(monkeypatch, capsys) -> None:
    called_with: dict[str, object] = {}

    def fake_run(application: str, **options: object) -> None:
        called_with["application"] = application
        called_with.update(options)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(run, "is_port_available", lambda: True)
    monkeypatch.setattr(run, "start_browser_opening", lambda: None)

    assert run.main() == 0
    assert called_with == {
        "application": "app.main:app",
        "host": "127.0.0.1",
        "port": 8000,
    }
    output = capsys.readouterr().out
    assert "AI Study Lab 0.1.0" in output
    assert "[2/3] Starting server" in output


def test_browser_opens_after_server_is_ready(monkeypatch, capsys) -> None:
    opened_urls: list[str] = []
    monkeypatch.setattr(run, "wait_until_ready", lambda: True)
    monkeypatch.setattr(run.webbrowser, "open", lambda url: opened_urls.append(url) or True)

    run.open_browser_when_ready()

    assert opened_urls == ["http://127.0.0.1:8000"]
    output = capsys.readouterr().out
    assert "[3/3] Opening browser" in output
    assert "Press Ctrl+C to stop" in output


def test_main_explains_when_port_is_busy(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run, "is_port_available", lambda: False)

    assert run.main() == 1
    assert "127.0.0.1:8000 is already in use" in capsys.readouterr().out
