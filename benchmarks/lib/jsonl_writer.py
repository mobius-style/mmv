"""Normalized JSONL output writer.

Schema (one row per sample):

  run_id          str           — identifier for the run; same for every row
  timestamp       str (ISO-8601) — when the row was committed
  model_profile   str            — key from model_profiles.yaml
  benchmark       str            — name from benchmark_matrix.yaml
  task            str            — subtask within benchmark (or '*')
  sample_id       str            — stable id from the dataset
  prompt_hash     str            — sha256 of the rendered prompt
  output_hash     str            — sha256 of the model response text
  score           float | None   — per-sample metric, runner-defined
  metric_name     str            — e.g. 'accuracy', 'exact_match', 'governance_score'
  latency_ms      int            — measured wall-clock
  tokens_in       int | None     — when known
  tokens_out      int | None     — when known
  error           str | None     — if non-null, score may be None and the row is a failure
  metadata        dict           — anything runner-specific (judgements, traces, …)
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8", "ignore")).hexdigest()


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


class JsonlWriter:
    """Append-only JSONL writer with strict schema validation.

    Use as a context manager so the file handle is flushed/closed cleanly.
    """

    REQUIRED = (
        "run_id", "timestamp", "model_profile", "benchmark", "task",
        "sample_id", "prompt_hash", "output_hash", "score", "metric_name",
        "latency_ms", "tokens_in", "tokens_out", "error", "metadata",
    )

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self.rows_written = 0

    def __enter__(self) -> "JsonlWriter":
        self._fh = self.path.open("a", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def write(self, row: dict[str, Any]) -> None:
        missing = [k for k in self.REQUIRED if k not in row]
        if missing:
            raise ValueError(f"row missing required fields: {missing}")
        if self._fh is None:
            raise RuntimeError("JsonlWriter used outside a `with` block")
        self._fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
        self.rows_written += 1


def read_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def make_row(
    *,
    run_id: str,
    model_profile: str,
    benchmark: str,
    task: str,
    sample_id: str,
    prompt: str,
    output: str,
    score: float | None,
    metric_name: str,
    latency_ms: int,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "timestamp": iso_now(),
        "model_profile": model_profile,
        "benchmark": benchmark,
        "task": task,
        "sample_id": sample_id,
        "prompt_hash": sha256(prompt),
        "output_hash": sha256(output),
        "score": score,
        "metric_name": metric_name,
        "latency_ms": int(latency_ms),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "error": error,
        "metadata": metadata or {},
    }
