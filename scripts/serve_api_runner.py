import atexit
from datetime import datetime
from pathlib import Path

from enterprise_agent_kb.api_server import serve_api


LOG_PATH = Path("tmp/api_runner.log")


def _log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


if __name__ == "__main__":
    atexit.register(lambda: _log("runner_exit"))
    try:
        _log("runner_start")
        serve_api(Path("knowledge_base"), host="127.0.0.1", port=8000)
        _log("runner_returned")
    except BaseException as exc:
        _log(f"runner_error {type(exc).__name__}: {exc}")
        raise
