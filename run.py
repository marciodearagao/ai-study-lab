"""Start AI Study Lab for local use."""

import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


APP_NAME = "AI Study Lab"
VERSION = (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip()
HOST = "127.0.0.1"
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{APP_URL}/health"


def is_port_available() -> bool:
    try:
        with socket.socket() as probe:
            probe.bind((HOST, PORT))
    except OSError:
        return False
    return True


def wait_until_ready(timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    return False


def open_browser_when_ready() -> None:
    if not wait_until_ready():
        print(f"\nThe browser was not opened. Visit {APP_URL} manually.", flush=True)
        return

    print("[3/3] Opening browser...", flush=True)
    print(f"\n{APP_NAME} is running at {APP_URL}", flush=True)
    print("Keep this terminal open. Press Ctrl+C to stop.\n", flush=True)
    try:
        opened = webbrowser.open(APP_URL)
    except Exception:
        opened = False
    if not opened:
        print(f"Open this URL manually: {APP_URL}", flush=True)


def start_browser_opening() -> None:
    threading.Thread(target=open_browser_when_ready, daemon=True).start()


def main() -> int:
    print(f"{APP_NAME} {VERSION}")
    print("Starting local application...\n")

    try:
        import uvicorn
    except ImportError:
        print('Startup failed: Uvicorn is not installed.')
        print('Run: python -m pip install -e ".[dev]"')
        return 1

    print("[1/3] Checking local address...", flush=True)
    if not is_port_available():
        print(f"\nStartup failed: {HOST}:{PORT} is already in use.")
        print("Stop the application using that port, then run `python run.py` again.")
        return 1

    print("[2/3] Starting server...", flush=True)
    start_browser_opening()

    try:
        uvicorn.run("app.main:app", host=HOST, port=PORT)
    except KeyboardInterrupt:
        pass
    except SystemExit as error:
        print("\nStartup failed. Check the server message above for details.")
        return error.code if isinstance(error.code, int) else 1
    except Exception as error:
        print(f"\nStartup failed: {error}")
        return 1

    print(f"\n{APP_NAME} stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
