"""Start/stop the demo app in a background thread (used by the pytest session fixture)."""

from __future__ import annotations

import threading
import time

import httpx
import uvicorn


class DemoServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host, self.port = host, port
        self.url = f"http://{host}:{port}"
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def healthy(self) -> bool:
        try:
            return httpx.get(f"{self.url}/health", timeout=1.0).status_code == 200
        except httpx.HTTPError:
            return False

    def start(self, timeout: float = 15.0) -> bool:
        """Start the server. Returns False when an instance is already running (it is reused)."""
        if self.healthy():
            return False
        from demo_app.app import create_app

        config = uvicorn.Config(create_app(), host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True, name="sdd-demo-app")
        self._thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.healthy():
                return True
            time.sleep(0.1)
        raise RuntimeError(f"Demo app did not start on {self.url} within {timeout}s")

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
