"""OPERATE-FR v0.1 suite runner.

CLI:
    python -m harness.run_eval \\
        --suite configs/suite_smoke.yaml \\
        --profile dummy \\
        --out reports/dummy_smoke.jsonl

Reads a suite YAML pointing to a dataset JSONL, invokes the adapter for
each task, classifies the route, and writes one JSONL record per task.
A single task failure is captured per-row, not allowed to crash the run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from .adapters import call_adapter
from .classify_route import RouteClassifier
from .schemas import make_result_record, validate_task

ROOT = Path(__file__).resolve().parent.parent


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[warn] skipping malformed line in {path}: {e}",
                      file=sys.stderr)
    return out


def _load_suite(suite_path: Path) -> dict[str, Any]:
    with suite_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_profile(profiles_path: Path, name: str) -> dict[str, Any]:
    with profiles_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    profiles = (data or {}).get("profiles", {})
    if name not in profiles:
        raise KeyError(
            f"profile {name!r} not in {profiles_path}; "
            f"available: {list(profiles.keys())}"
        )
    prof = dict(profiles[name])
    # resolve $ENV interpolation
    for k, v in list(prof.items()):
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            env_name = v[2:-1]
            import os
            prof[k] = os.environ.get(env_name, v)
    return prof


def _build_prompt(task: dict[str, Any]) -> str:
    """v0.1: pass the user prompt through verbatim.

    Future versions may add tool_mode framing / system header; in v0.1 we
    keep it bare so the classifier's signals reflect the model's
    untouched output.
    """
    return task["user_prompt"]


def run(
    suite_path: Path,
    profile_name: str,
    out_path: Path,
    profiles_path: Path | None = None,
    limit: int | None = None,
) -> dict:
    suite = _load_suite(suite_path)
    dataset_path = (ROOT / suite["dataset"]).resolve()
    profiles_path = (
        profiles_path or (ROOT / suite.get("profiles_file",
                                            "configs/model_profiles.example.yaml"))
    ).resolve()
    profile = _load_profile(profiles_path, profile_name)

    tasks = _read_jsonl(dataset_path)
    if limit is not None and limit > 0:
        tasks = tasks[:limit]

    classifier = RouteClassifier()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "total": len(tasks),
        "ran": 0,
        "errored": 0,
        "started_at": time.time(),
        "suite": suite.get("name", suite_path.stem),
        "profile": profile_name,
    }

    print(
        f"[operate-fr] suite={summary['suite']} profile={profile_name} "
        f"tasks={len(tasks)} → {out_path}",
        flush=True,
    )

    with out_path.open("w", encoding="utf-8") as fh:
        for i, task in enumerate(tasks, 1):
            errs = validate_task(task)
            if errs:
                fh.write(json.dumps({
                    "task_id": task.get("id", f"unknown_{i}"),
                    "suite": summary["suite"],
                    "profile": profile_name,
                    "model_id": profile.get("model_id"),
                    "response_text": "",
                    "tool_calls": [],
                    "classified_route": None,
                    "classified_confidence": 0.0,
                    "classified_evidence": {},
                    "classified_notes": "",
                    "latency_ms": 0,
                    "tokens_in": None,
                    "tokens_out": None,
                    "error": f"task schema invalid: {errs}",
                    "metadata": {"family": task.get("family")},
                }, ensure_ascii=False) + "\n")
                summary["errored"] += 1
                continue

            prompt = _build_prompt(task)
            ar = call_adapter(prompt, profile)

            # 120B post-route validator (rule-based, family-aware).
            # Runs only when the profile opts in. The validator may rewrite
            # the response BEFORE classification so the harness measures
            # the corrected output, not the raw model output.
            pv_notes: list[str] = []
            pv_rewritten = False
            pv_family = None
            if profile.get("post_validator") and ar.error is None and ar.text:
                from .route_transformer import post_validate  # local import
                pv = post_validate(prompt, ar.text)
                if pv.rewritten:
                    ar.text = pv.text
                pv_notes = pv.notes
                pv_rewritten = pv.rewritten
                pv_family = pv.family

            # MMV-S-RC3.3 Small Routing Stabilizer — profile-gated.
            # Runs ONLY when `small_routing_stabilizer: true` is set on
            # the profile. Does NOT activate for Large RC3.3 profiles or
            # raw baselines. Applied as a final correction layer AFTER
            # the route-transformer / post-validator.
            srs_interventions: list[str] = []
            srs_rewritten = False
            srs_family = None
            if (profile.get("small_routing_stabilizer")
                    and ar.error is None and ar.text):
                from .small_routing_stabilizer import apply as srs_apply  # local

                # v1.1 — broad-definition pass-through re-call.
                # Profile-gated by `broad_definition_passthrough: true`.
                # The recall builds a RAW Ollama profile (no RoutingEngine,
                # no post-cal) and asks the model directly. Returns the
                # plain text answer. The Stabilizer uses this only when
                # the upstream pipeline emitted a generic clarify on a
                # broad stable entity-definition prompt.
                recall_fn = None
                if profile.get("broad_definition_passthrough"):
                    def _recall_broad_def(p_text: str) -> str:
                        raw_profile = {
                            "backend": "ollama",
                            "endpoint": profile.get(
                                "target_endpoint",
                                "http://localhost:11434",
                            ),
                            "model_id": profile.get("model_id", "qwen3.5:9b"),
                            "temperature": float(profile.get("temperature", 0.0)),
                            "max_tokens": int(profile.get("max_tokens", 1024)),
                            "timeout_s": int(profile.get("timeout_s", 120)),
                            "retry": 1,
                            "extra": {"think": False},
                        }
                        r = call_adapter(p_text, raw_profile)
                        return r.text or ""
                    recall_fn = _recall_broad_def

                srs = srs_apply(prompt, ar.text, recall_fn=recall_fn)
                if srs.rewritten:
                    ar.text = srs.text
                srs_interventions = srs.interventions
                srs_rewritten = srs.rewritten
                srs_family = srs.inferred_family

            classified = classifier.classify(prompt, ar.text, ar.tool_calls)

            # Adapter-side route-transformer audit fields, if present
            rt_family = getattr(ar, "__dict__", {}).get(
                "route_transformer_family",
            )
            rt_injected = getattr(ar, "__dict__", {}).get(
                "route_transformer_injected",
            )

            rec = make_result_record(
                task_id=task["id"],
                suite=summary["suite"],
                profile=profile_name,
                model_id=ar.model_id,
                response_text=ar.text,
                tool_calls=ar.tool_calls,
                classified=classified,
                latency_ms=ar.latency_ms,
                tokens_in=ar.tokens_in,
                tokens_out=ar.tokens_out,
                error=ar.error,
                metadata={
                    "family": task.get("family"),
                    "domain": task.get("domain"),
                    "language": task.get("language"),
                    "tool_mode": task.get("tool_mode"),
                    "temporal_volatility": task.get("temporal_volatility"),
                    # OPERATE-FR-120B route-transformer audit
                    "route_transformer_family": rt_family,
                    "route_transformer_injected": rt_injected,
                    "post_validator_family": pv_family,
                    "post_validator_rewritten": pv_rewritten,
                    "post_validator_notes": pv_notes,
                },
            )
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            summary["ran"] += 1
            if ar.error:
                summary["errored"] += 1
            if i % 10 == 0 or i == len(tasks):
                print(
                    f"  [{i}/{len(tasks)}] {task['id']} "
                    f"route={classified['route']} "
                    f"lat={ar.latency_ms}ms err={ar.error or '—'}",
                    flush=True,
                )

    summary["finished_at"] = time.time()
    summary["wall_s"] = round(summary["finished_at"] - summary["started_at"], 2)
    print(f"[operate-fr] done. wall={summary['wall_s']}s ran={summary['ran']} "
          f"errored={summary['errored']}", flush=True)
    return summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OPERATE-FR v0.1 runner")
    p.add_argument("--suite", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--profiles-file", default=None,
                   help="override profiles YAML (otherwise from suite or default)")
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=None,
                   help="for smoke-of-smoke runs; cap number of tasks")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    run(
        suite_path=Path(args.suite),
        profile_name=args.profile,
        out_path=Path(args.out),
        profiles_path=Path(args.profiles_file) if args.profiles_file else None,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
