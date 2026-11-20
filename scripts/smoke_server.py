"""One foreground server startup check; no paid, remote, or background job calls."""

import os
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    result = {}

    def probe():
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/_stcore/health", timeout=2
            ) as response:
                result["status"] = response.status
                result["body"] = response.read(100).decode()
        except Exception as exc:
            result["error"] = type(exc).__name__

    with tempfile.TemporaryDirectory() as directory:
        timer = threading.Timer(4, probe)
        timer.start()
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    "app.py",
                    "--server.headless=true",
                    "--server.address=127.0.0.1",
                    f"--server.port={port}",
                ],
                cwd=repo,
                env={
                    **os.environ,
                    "AMR_READ_ONLY": "true",
                    "AMR_AI_ENABLED": "false",
                    "AMR_DB_PATH": str(Path(directory) / "empty.sqlite3"),
                },
                capture_output=True,
                text=True,
                timeout=8,
            )
            print(completed.stdout)
            print(completed.stderr)
            result["early_exit"] = completed.returncode
        except subprocess.TimeoutExpired:
            # subprocess.run kills and waits for its child on timeout.
            pass
        finally:
            timer.join()
    print("Loopback startup health:", result)
    if result.get("status") != 200 or result.get("body") != "ok" or "early_exit" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
