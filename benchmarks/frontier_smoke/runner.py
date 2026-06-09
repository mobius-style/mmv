"""Phase 3 — runner for one (condition, bench) pair.

Reads the sampled CSV, builds prompts per spec §3.2, calls the harness
adapter, applies routing precedence + parser, and appends one JSONL row
per question. Robust to mid-run interruption: rows are flushed per call.

CLI:
  python -m benchmarks.frontier_smoke.runner \\
    --bench mmlu_pro \\
    --condition mmv_medium \\
    --outdir bench/frontier_smoke_<ts>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "operate-fr-bench"))

from harness import adapters as adapters_mod
from harness import classify_route

from benchmarks.frontier_smoke.parser import (
    apply_routing_precedence,
    parse_letter,
    parse_number,
    score_simpleqa,
)


# ─── condition → profile mapping (spec §2) ───────────────────────────────

CONDITION_TO_PROFILE = {
    "raw_qwen35_9b":      "open_weight_local_9b_no_tool",
    "mmv_small":          "mmv_small_rc3_3_stabilized",
    "raw_gemma4_26b":     "raw_gemma4_26b_no_tool",
    "mmv_medium":         "gemma4_26b_route_transformer_plus_validator_v3_1",
    "raw_gpt_oss_120b":   "raw_gpt_oss_120b_frontier_bench",
    "mmv_large":          "120b_route_transformer_plus_validator_v3_1",
}

CONDITION_TO_BASE_MODEL = {
    "raw_qwen35_9b":     "qwen3.5:9b",
    "mmv_small":         "qwen3.5:9b",
    "raw_gemma4_26b":    "gemma4:26b",
    "mmv_medium":        "gemma4:26b",
    "raw_gpt_oss_120b":  "openai/gpt-oss-120b",
    "mmv_large":         "openai/gpt-oss-120b",
}

CONDITION_TO_HARNESS = {
    "raw_qwen35_9b":     "none",
    "mmv_small":         "small_routing_stabilizer_rc3_3_v1",
    "raw_gemma4_26b":    "none",
    "mmv_medium":        "temporal_governance_v3_1_base_override",
    "raw_gpt_oss_120b":  "none",
    "mmv_large":         "temporal_governance_v3_1",
}

CONDITION_TO_ENDPOINT = {
    "raw_qwen35_9b":    "ollama_local",
    "mmv_small":        "ollama_local",
    "raw_gemma4_26b":   "ollama_local",
    "mmv_medium":       "ollama_local",
    "raw_gpt_oss_120b": "groq_api",
    "mmv_large":        "groq_api",
}

IS_MMV = {
    "raw_qwen35_9b": False, "mmv_small": True,
    "raw_gemma4_26b": False, "mmv_medium": True,
    "raw_gpt_oss_120b": False, "mmv_large": True,
}

PROFILES_YAML = REPO_ROOT / "operate-fr-bench" / "configs" / "model_profiles.example.yaml"


# ─── prompt templates (spec §3.2) ────────────────────────────────────────

def prompt_mmlu_pro(question: str, options: list[str]) -> str:
    letters = "ABCDEFGHIJ"
    lines = [
        "Answer the following multiple-choice question. Output only the "
        "letter of the correct answer. Do not include any explanation or "
        "additional text.",
        "",
        f"Question: {question}",
        "",
        "Options:",
    ]
    for i, opt in enumerate(options):
        lines.append(f"{letters[i]}. {opt}")
    lines += ["", "Answer:"]
    return "\n".join(lines)


def prompt_gpqa(question: str, options: list[str]) -> str:
    letters = "ABCD"
    lines = [
        "Answer the following multiple-choice question from physics, "
        "chemistry, or biology. Output only the letter of the correct "
        "answer (A, B, C, or D). Do not include any explanation.",
        "",
        f"Question: {question}",
        "",
    ]
    for i, opt in enumerate(options[:4]):
        lines.append(f"{letters[i]}. {opt}")
    lines += ["", "Answer:"]
    return "\n".join(lines)


def prompt_truthfulqa(question: str, options: list[str]) -> str:
    lines = [
        "Choose the most truthful answer to the question below. Output "
        "only the number of the correct answer. Do not include any "
        "explanation.",
        "",
        f"Question: {question}",
        "",
    ]
    for i, opt in enumerate(options):
        lines.append(f"{i+1}. {opt}")
    lines += ["", "Answer:"]
    return "\n".join(lines)


def prompt_simpleqa(question: str) -> str:
    return (
        "Answer the following short-answer question. If you do not know "
        "the answer with high confidence, respond exactly with \"I don't "
        "know\" — do not guess. Otherwise respond with the answer as "
        "concisely as possible (single fact, no explanation).\n\n"
        f"Question: {question}\n\nAnswer:"
    )


BENCH_TO_BUILDER = {
    "mmlu_pro":        ("letter", prompt_mmlu_pro,    "ABCDEFGHIJ"),
    "gpqa_diamond":    ("letter", prompt_gpqa,        "ABCD"),
    "truthfulqa_mc1":  ("number", prompt_truthfulqa,  None),
    "simpleqa":        ("openend", prompt_simpleqa,   None),
}


# ─── routing decision normalization ──────────────────────────────────────

def derive_routing_decision(
    prompt: str, response: str, condition: str,
) -> Optional[str]:
    """For MMV conditions, run classify_route on the response and normalize.

    Returns one of {answer, ask, verify, abstain, re_anchor}, or None for
    raw conditions where no routing is applied.
    """
    if not IS_MMV[condition]:
        return None
    cls = classify_route.classify(prompt, response)
    route = cls.get("route") or "answer"
    ev = cls.get("evidence") or {}
    # Treat date_bound_answer as a sub-type of "answer" — model still answered,
    # just framed with date boundary. The spec routing_decision vocabulary
    # is {answer, ask, verify, abstain, re_anchor}.
    if route == "date_bound_answer":
        return "answer"
    # Explicit abstain via refusal-with-no-answer-pattern
    if route == "abstain":
        return "abstain"
    if ev.get("abstain_detected") or (
        ev.get("refusal_dominant") and ev.get("refusal_in_lead")
    ):
        return "abstain"
    if route in ("answer", "ask", "verify", "re_anchor"):
        return route
    return "answer"


# ─── core run loop ───────────────────────────────────────────────────────

def _load_profile(profile_name: str) -> dict:
    with PROFILES_YAML.open() as fh:
        data = yaml.safe_load(fh)
    return data["profiles"][profile_name]


def _ts_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_sampled(csv_path: Path) -> list[dict]:
    out = []
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            options = json.loads(row["options_json"]) if row["options_json"] else []
            out.append({
                "question_id": row["question_id"],
                "subject_or_category": row["subject_or_category"],
                "question": row["question"],
                "options": options,
                "expected": row["expected"],
            })
    return out


def run(bench: str, condition: str, outdir: Path,
        limit: Optional[int] = None,
        run_id: Optional[str] = None) -> dict:
    if bench not in BENCH_TO_BUILDER:
        raise ValueError(f"unknown bench: {bench}")
    if condition not in CONDITION_TO_PROFILE:
        raise ValueError(f"unknown condition: {condition}")

    parser_kind, prompt_builder, valid_letters = BENCH_TO_BUILDER[bench]
    profile = _load_profile(CONDITION_TO_PROFILE[condition])
    base_model = CONDITION_TO_BASE_MODEL[condition]
    harness_name = CONDITION_TO_HARNESS[condition]
    endpoint = CONDITION_TO_ENDPOINT[condition]
    run_id = run_id or f"frontier_smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    csv_path = outdir / "datasets" / f"sampled_{bench}.csv"
    questions = _read_sampled(csv_path)
    if limit is not None:
        questions = questions[:limit]

    out_jsonl = outdir / "results" / f"results_{bench}_{condition}.jsonl"
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    n_parse_fail = 0
    n_processed = 0
    n_errored = 0
    t_start = time.time()
    print(f"[START] {condition} / {bench} → {out_jsonl} (n={len(questions)})",
          flush=True)

    with out_jsonl.open("w", encoding="utf-8") as fh:
        for q in questions:
            # 1. build user prompt
            if bench == "simpleqa":
                user_prompt = prompt_builder(q["question"])
                max_choices = None
            elif parser_kind == "letter":
                user_prompt = prompt_builder(q["question"], q["options"])
                max_choices = len(q["options"])
            else:  # number
                user_prompt = prompt_builder(q["question"], q["options"])
                max_choices = len(q["options"])

            # 2. call adapter
            t0 = time.time()
            try:
                ar = adapters_mod.call_adapter(user_prompt, profile)
            except Exception as e:
                ar = adapters_mod.AdapterResult(
                    text="", tool_calls=[],
                    latency_ms=int((time.time() - t0) * 1000),
                    tokens_in=None, tokens_out=None,
                    error=f"call_adapter exception: {type(e).__name__}: {e}",
                    model_id=profile.get("model_id", "?"),
                )

            response = ar.text or ""
            error = ar.error
            if error:
                n_errored += 1

            # 3. routing decision (MMV only)
            routing_decision = derive_routing_decision(
                user_prompt, response, condition,
            )

            # 4. routing precedence first
            override = apply_routing_precedence(routing_decision)
            if override is not None:
                parsed = None
                parse_layer = "routing_override"
                parse_failure = False
                strict_correct = False
                conditional_correct = None
                verdict = "routing_override" if bench == "simpleqa" else None
                scoring_layer = "routing_override" if bench == "simpleqa" else None
                abstain_detected = False
                needs_judge_review = False
            else:
                # 5. parse / score per bench
                if bench == "simpleqa":
                    res = score_simpleqa(response, q["expected"],
                                         routing_decision=routing_decision)
                    parsed = res.parsed
                    parse_layer = res.scoring_layer
                    parse_failure = (res.verdict == "incorrect" and
                                     res.scoring_layer == "empty_response")
                    abstain_detected = res.abstain_detected
                    needs_judge_review = res.needs_judge_review
                    verdict = res.verdict
                    scoring_layer = res.scoring_layer
                    if res.verdict == "correct":
                        strict_correct = True
                        conditional_correct = True
                    elif res.verdict == "abstain":
                        strict_correct = False
                        conditional_correct = None  # excluded from conditional
                    elif res.verdict == "judge_review":
                        strict_correct = False  # not counted as correct yet
                        conditional_correct = None  # excluded
                    else:  # incorrect
                        strict_correct = False
                        conditional_correct = False
                else:
                    if parser_kind == "letter":
                        pr = parse_letter(response, valid_letters=valid_letters)
                    else:
                        pr = parse_number(response, max_choices=max_choices)
                    parsed = pr.parsed
                    parse_layer = pr.layer
                    parse_failure = pr.parse_failure
                    if parse_failure:
                        n_parse_fail += 1
                    abstain_detected = False
                    needs_judge_review = False
                    verdict = None
                    scoring_layer = None
                    if pr.parse_failure:
                        strict_correct = False
                        conditional_correct = None  # excluded from conditional
                    else:
                        is_match = (parsed == q["expected"])
                        strict_correct = is_match
                        conditional_correct = is_match

            # 6. assemble row + flush
            row = {
                "run_id": run_id,
                "question_id": q["question_id"],
                "bench": bench,
                "subject_or_category": q["subject_or_category"],
                "condition": condition,
                "base_model": base_model,
                "harness": harness_name,
                "user_prompt": user_prompt,
                "system_prompt_or_prefix_used": IS_MMV[condition],
                "routing_decision": routing_decision,
                "response_raw": response,
                "response_parsed": parsed,
                "expected_answer": q["expected"],
                "strict_correct": strict_correct,
                "conditional_correct": conditional_correct,
                "verdict": verdict,
                "parse_layer": parse_layer,
                "parse_failure": parse_failure,
                "abstain_detected": abstain_detected,
                "needs_judge_review": needs_judge_review,
                "scoring_layer": scoring_layer,
                "latency_ms": ar.latency_ms,
                "input_tokens": ar.tokens_in,
                "output_tokens": ar.tokens_out,
                "timestamp": _ts_now(),
                "endpoint": endpoint,
                "raw_completion_metadata": {
                    "error": error,
                    "route_transformer_injected":
                        getattr(ar, "route_transformer_injected", None),
                    "route_transformer_family":
                        getattr(ar, "route_transformer_family", None),
                    "post_validator_rewritten":
                        getattr(ar, "post_validator_rewritten", None),
                    "post_validator_notes":
                        getattr(ar, "post_validator_notes", None),
                    "model_id_reported": ar.model_id,
                },
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            n_processed += 1

            # Progress log every 25
            if n_processed % 25 == 0 or n_processed == len(questions):
                elapsed = time.time() - t_start
                pf = n_parse_fail / max(1, n_processed)
                print(f"  [{n_processed}/{len(questions)}] "
                      f"pf={pf:.0%} err={n_errored} "
                      f"avg_lat={elapsed/n_processed*1000:.0f}ms",
                      flush=True)

            # Abort: parse_failure rate > 15% after at least 20 calls
            if n_processed >= 20 and (n_parse_fail / n_processed) > 0.15:
                print(f"[ABORT] parse_failure_rate "
                      f"{n_parse_fail/n_processed:.0%} > 15% "
                      f"after {n_processed} calls — stopping", flush=True)
                break

    elapsed = time.time() - t_start
    pf_rate = n_parse_fail / max(1, n_processed)
    print(f"[DONE] {condition} / {bench}: "
          f"{n_processed}/{len(questions)}, pf={pf_rate:.0%}, "
          f"err={n_errored}, wall={elapsed:.1f}s", flush=True)
    return {
        "n_processed": n_processed,
        "n_parse_fail": n_parse_fail,
        "n_errored": n_errored,
        "wall_s": elapsed,
        "parse_failure_rate": pf_rate,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    run(args.bench, args.condition, Path(args.outdir),
        limit=args.limit, run_id=args.run_id)


if __name__ == "__main__":
    main()
