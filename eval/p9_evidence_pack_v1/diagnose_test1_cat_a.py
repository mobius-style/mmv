#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 1 Cat A diagnostic breakdown.

Per Phase 5C amendment: when Cat A in Test 1 comes out high, classify
each Cat A entry into:

  A-hard       — clear conversation breakdown, wrong factual answer, or
                 dangerous route (e.g., abstain expected but answered).
                 *Heuristic-only here* — confirming requires reading the
                 generated text; we mark candidates and flag for manual.
  A-route      — expected/actual route mismatch with no contextual or
                 harness mitigation; the routing layer made an
                 actionable error.
  A-context    — the prompt is referential/continuation and only makes
                 sense given prior turns; the pseudo-UI harness uses a
                 fresh session per query (single-turn), so this Cat A
                 is at least partly a harness-design artefact.
  A-judge      — the expected_route assignment is plausibly too strict.
                 The AI interpreting the prompt as a "meta_question /
                 self_referential" instruction (capability question)
                 and answering accordingly is debatable, not clearly
                 wrong.
  A-retrieval  — Pattern Library / top-1 retrieval clearly steered the
                 route. Useful signal: top_score either very high (false
                 positive) or very low (default-route fallback).
  A-model      — route was reasonable but the small-model generation
                 quality made the turn Cat A. **Not measured this pass**
                 — we did not capture response_text in the per-query
                 trace and Phase 5C forbids repair work. Recorded as
                 "deferred" with a placeholder count of 0.

This script reads the existing per-query JSONL produced by
run_test1_holdout.py and classifies each Cat A row using the rules
above. It does NOT re-run the routing engine.

Output:
  cat_a_diagnostic.json  — per-bucket counts, rates, and 10–20 examples
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
PER_QUERY = OUT_DIR / "holdout_eval_results.jsonl"
SUMMARY = OUT_DIR / "holdout_eval_results.json"
DIAG_OUT = OUT_DIR / "cat_a_diagnostic.json"


# Phrases that strongly mark a query as referential / continuation —
# these prompts need prior conversation context to interpret correctly.
REFERENTIAL_STARTERS = (
    "And ", "Also ", "Now ", "Pick up", "Continue", "Resume", "Onwards",
    "Onto", "Like the", "Same as", "As we", "As default", "Take it",
    "Build on", "Apply that", "Run it", "Repeat with", "More on",
    "Tell me more", "Go on", "Wrap up", "Drill into", "Push it",
    "Develop this", "Where do we go", "Anything else", "Add to that",
    "Add the", "Add an example", "Expand on", "Elaborate", "Take it further",
    "Try the other", "That's not", "It still", "Keep going", "Just keep",
    "Try with different", "Use the other", "And after", "And of",
    "What's the follow-up", "Then?", "And then?",
)

REFERENTIAL_EXACTS = {
    "Continue.", "Continue please.", "Keep going.", "Just keep going.",
    "More.", "Less.", "Faster.", "Slower please.", "Different.",
    "And then?", "Next step?", "Onwards.", "Got it.", "More on that.",
    "Tell me more.", "Go on.", "And after that?", "Okay, what's next?",
}

# Phrases that read as direct instructions to the AI; "self_referential"
# / "meta_question" answer is a defensible interpretation.
META_INSTRUCTION_HINTS = (
    "Help me", "Can you", "Could you", "Would you", "Will you",
    "Please ", "Try harder", "Take a look", "Show me",
    "Walk me through", "Tell me about", "Let me know what you think",
    "Choose for me", "Pick the better", "Whatever works",
    "Make it ", "Give me your opinion",
    "What do you think", "What should I do",
    "I need help", "Try again", "Go deeper",
)


def classify(row: dict) -> tuple[str, str]:
    """Return (bucket, rationale). bucket ∈ {A-hard, A-route,
    A-context, A-judge, A-retrieval, A-model}.
    """
    q = (row.get("query") or "").strip()
    rcs = set(row.get("reason_codes") or [])
    cat = row.get("category", "")
    intent = row.get("intent_type", "")
    score = row.get("top_score")
    actual = row.get("actual_route", "")
    expected = row.get("expected_route", "")

    # A-hard: dangerous route. None of our holdout queries are
    # safety-relevant (no expected=abstain). A response of 'answer'
    # when expected was 'verify' for time-sensitive facts is
    # potentially A-hard, but we cannot confirm without the response
    # text — mark conservatively as candidate, not confirmed.
    if expected == "abstain" and actual == "answer":
        return ("A-hard", "expected=abstain but routed to answer (safety failure)")

    # A-context: continuation / referential prompts that need prior
    # turns. PseudoUISession in run_test1_holdout uses a fresh session
    # per query, so these are partly harness artefacts.
    if cat == "continuation":
        return ("A-context",
                "continuation category; single-turn harness lacks prior "
                "context required to interpret")
    if q in REFERENTIAL_EXACTS:
        return ("A-context",
                "exact referential phrase; needs prior turn context")
    if any(q.startswith(s) for s in REFERENTIAL_STARTERS):
        return ("A-context",
                "starts with referential token; needs prior turn context")

    # A-judge: the AI plausibly interprets the prompt as a meta-question
    # ("can you ...?", "help me ...") and "answer" is a defensible route
    # (acknowledge capability + invite specifics) rather than a strict
    # "ask".
    if "self_referential" in rcs or intent == "meta_question":
        return ("A-judge",
                f"AI classified as meta/self-referential (rcs={list(rcs)[:3]}); "
                "expected=ask is plausibly over-strict")
    if any(q.startswith(s) or (" " + s.strip(" ") + " ") in (" " + q + " ")
           for s in META_INSTRUCTION_HINTS):
        return ("A-judge",
                "prompt reads as direct instruction to the AI; "
                "expected=ask is plausibly over-strict")

    # A-retrieval: top-1 retrieval signal evidently dominated the
    # routing decision.
    if score is None:
        return ("A-route", "no top-1 retrieval signal; routing decided answer "
                "without retrieval support")
    if score >= 0.85:
        return ("A-retrieval",
                f"high-confidence Pattern Library match (top1={score:.3f}) "
                "steered the route into answer")
    if score < 0.50:
        return ("A-route", f"weak retrieval (top1={score:.3f}); fallback "
                "answer route despite under-specified prompt")

    # A-model: route was answer/verify and we'd need response_text to
    # judge. This pass does not capture response_text — bucket exists
    # for completeness only.
    # (Effectively unreachable here because we exhaust the other
    # buckets first; left as fallback.)
    return ("A-route",
            f"route divergence (expected={expected} actual={actual}, "
            f"top1={score})")


def main() -> int:
    if not PER_QUERY.exists():
        print(f"missing: {PER_QUERY}", file=sys.stderr)
        return 1

    rows = []
    for line in PER_QUERY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

    n_total = len(rows)
    a_rows = [r for r in rows if r.get("cat") == "A"]
    n_a = len(a_rows)

    buckets = {}
    for r in a_rows:
        b, why = classify(r)
        r["_a_bucket"] = b
        r["_a_bucket_why"] = why
        buckets.setdefault(b, []).append(r)

    counts = {b: len(v) for b, v in buckets.items()}
    rates = {b: round(len(v) / n_total, 4) for b, v in buckets.items()}

    # Representative examples — at least 3 per bucket, up to 5; capped
    # at 20 across all buckets for readability.
    examples = []
    per_bucket_target = 3
    extra_pool = []
    for b, vs in buckets.items():
        for r in vs[:per_bucket_target]:
            examples.append({
                "id": r["id"],
                "category": r["category"],
                "query": r["query"],
                "expected_route": r["expected_route"],
                "actual_route": r["actual_route"],
                "top_score": r.get("top_score"),
                "reason_codes": (r.get("reason_codes") or [])[:4],
                "intent_type": r.get("intent_type", ""),
                "a_bucket": b,
                "rationale": r["_a_bucket_why"],
            })
        for r in vs[per_bucket_target:]:
            extra_pool.append((b, r))

    # Top up to 20 examples total.
    while len(examples) < 20 and extra_pool:
        b, r = extra_pool.pop(0)
        examples.append({
            "id": r["id"],
            "category": r["category"],
            "query": r["query"],
            "expected_route": r["expected_route"],
            "actual_route": r["actual_route"],
            "top_score": r.get("top_score"),
            "reason_codes": (r.get("reason_codes") or [])[:4],
            "intent_type": r.get("intent_type", ""),
            "a_bucket": b,
            "rationale": r["_a_bucket_why"],
        })

    out = {
        "test": "p9_evidence_pack_v1.test_1_cat_a_diagnostic",
        "n_total": n_total,
        "n_cat_A": n_a,
        "cat_A_rate": round(n_a / n_total, 4),
        "bucket_counts": counts,
        "bucket_rates_over_total": rates,
        "bucket_rates_within_cat_a": {
            b: round(c / n_a, 4) if n_a else 0.0
            for b, c in counts.items()
        },
        # Convenience aggregates the user requested:
        "hard_cat_a_rate":              round(counts.get("A-hard", 0) / n_total, 4),
        "route_mismatch_rate":          round(counts.get("A-route", 0) / n_total, 4),
        "context_harness_rate":         round(counts.get("A-context", 0) / n_total, 4),
        "judge_strictness_rate":        round(counts.get("A-judge", 0) / n_total, 4),
        "retrieval_failure_rate":       round(counts.get("A-retrieval", 0) / n_total, 4),
        "model_quality_rate_deferred":  0.0,  # not measured this pass

        "examples": examples,
        "method": {
            "classifier": "heuristic, rule-based",
            "uses_response_text": False,
            "limitations": [
                "A-hard requires response-text inspection to confirm; only "
                "structural signal (expected=abstain & actual=answer) used here.",
                "A-model requires response-text inspection; not measured "
                "this pass and Phase 5C forbids repair work.",
                "A-context is heuristic on referential markers + the "
                "'continuation' category label.",
                "A-judge is heuristic on self_referential / meta_question "
                "intent; some entries flagged here may genuinely be Cat A.",
            ],
        },
        "note_on_phase4_difference": (
            "Phase 4's long-tail Cat A = 0/505 measurement was based on "
            "annotation-vs-top-pattern_id at retrieval thresholds; it "
            "asked 'did Pattern Library lookup land on the right pattern, "
            "or fall through cleanly?'. The Phase 5C Test 1 measurement "
            "asks a different question: 'does the routing layer's actual "
            "route match the expected route?'. The two are NOT directly "
            "comparable. A high Phase 5C Cat A rate does not contradict "
            "Phase 4's 0/505 finding; they are different surfaces."
        ),
    }

    DIAG_OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {DIAG_OUT}")
    print(f"counts: {counts}")
    print(f"rates over total: {rates}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
