"""
inference_manager.py — Manages Ollama instance discovery.

Lazy singleton. Never calls subprocess on import.
In test mode, returns default ports without probing.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import os


class InferenceManager:
    _test_mode: bool = False
    _ready: bool = False
    _ports: list[int] = []
    _mode: str = "single"

    @classmethod
    def set_test_mode(cls):
        cls._test_mode = True

    def _ensure_setup(self):
        if not self._ready:
            self._setup()

    @property
    def mode(self) -> str:
        self._ensure_setup()
        return self._mode

    @property
    def ports(self) -> list[int]:
        self._ensure_setup()
        return self._ports

    @property
    def second_endpoint(self) -> str | None:
        self._ensure_setup()
        if len(self._ports) >= 2:
            return f"http://localhost:{self._ports[1]}"
        return None

    @property
    def status(self) -> dict:
        self._ensure_setup()
        return {"mode": self._mode, "ports": self._ports, "ready": self._ready}

    def _setup(self):
        if self._test_mode:
            self._mode = "single"
            self._ports = [11434]
            self._ready = True
            return

        self._ports = [11434]
        port2 = int(os.environ.get("OLLAMA_PORT_2", "11435"))

        try:
            import requests
            resp = requests.get(f"http://localhost:{port2}/api/tags", timeout=2)
            if resp.status_code == 200:
                self._ports.append(port2)
                self._mode = "pipeline"
        except Exception:
            pass

        self._ready = True


# Lazy singleton — _setup() is NOT called on import
inference_manager = InferenceManager()
