#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 2 structural post-hoc analysis.

Phase 5C run captured raw_response + governed_response for 60 sampled
queries via Ollama on both sides; the Groq judge returned HTTP 403 on
all calls (account-level auth issue), so n_judged = 0 and the test's
primary signal is INCONCLUSIVE_NO_JUDGE.

To salvage a small structural signal from the captured pairs without
re-introducing a judge or modifying source code, this script computes
*structural features only* on the already-captured text:

  length_chars                     : len(text)
  ends_with_question               : last non-empty sentence ends '?'
  contains_clarifying_question     : '?' anywhere
  mentions_verify_language         : verify / check / confirm /
                                     up-to-date / latest / current /
                                     as of / I don't have access /
                                     I'm not sure
  mentions_freshness_caveat        : 'as of', 'my knowledge', 'cutoff',
                                     'may have changed', 'updated'

Aggregation:
  - per-side means and rates
  - per-category breakdown
  - particularly: ambiguous_underspecified / continuation rates of
    `ends_with_question` (a structural proxy for "asked back")

This is NOT a judgment substitute. It's a transparent structural
counter on existing artifacts, suitable for a paper footnote.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PER_QUERY = ROOT / "raw_vs_governed_per_query.jsonl"
OUT = ROOT / "raw_vs_governed_structural_post_hoc.json"

VERIFY_RX = re.compile(
    r"\b(verify|check|confirm|up-?to-?date|latest|current|as of|"
    r"i don'?t have (?:access|the latest)|i'?m not sure|"
    r"i don'?t know)\b",
    re.IGNORECASE,
)
FRESH_RX = re.compile(
    r"\b(as of|my (?:knowledge|training)|knowledge cutoff|cutoff|"
    r"may have changed|updated|recent (?:data|update))\b",
    re.IGNORECASE,
)


def features(text: str) -> dict:
    if not text:
        return {
            "length_chars": 0,
            "ends_with_question": False,
            "contains_question": False,
            "mentions_verify": False,
            "mentions_freshness": False,
            "is_empty": True,
        }
    t = text.strip()
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', t) if s]
    last = sentences[-1].rstrip() if sentences else t
    return {
        "length_chars": len(t),
        "ends_with_question": last.endswith("?"),
        "contains_question": "?" in t,
        "mentions_verify": bool(VERIFY_RX.search(t)),
        "mentions_freshness": bool(FRESH_RX.search(t)),
        "is_empty": False,
    }


def main() -> int:
    rows = []
    for line in PER_QUERY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    print(f"loaded {len(rows)} pairs")

    by_cat = {}
    overall_raw = []
    overall_gov = []
    for r in rows:
        cat = r["category"]
        raw_f = features(r.get("raw_response", ""))
        gov_f = features(r.get("governed_response", ""))
        overall_raw.append(raw_f)
        overall_gov.append(gov_f)
        by_cat.setdefault(cat, []).append((raw_f, gov_f, r))

    def agg(side):
        n = len(side)
        if n == 0:
            return {}
        return {
            "n": n,
            "mean_length_chars": round(sum(s["length_chars"] for s in side) / n, 1),
            "ends_with_question_rate": round(sum(1 for s in side if s["ends_with_question"]) / n, 4),
            "contains_question_rate": round(sum(1 for s in side if s["contains_question"]) / n, 4),
            "mentions_verify_rate": round(sum(1 for s in side if s["mentions_verify"]) / n, 4),
            "mentions_freshness_rate": round(sum(1 for s in side if s["mentions_freshness"]) / n, 4),
            "empty_rate": round(sum(1 for s in side if s["is_empty"]) / n, 4),
        }

    out = {
        "test": "p9_evidence_pack_v1.test_2_structural_post_hoc",
        "context": (
            "Test 2's primary signal was INCONCLUSIVE_NO_JUDGE because "
            "the Groq judge endpoint returned HTTP 403 across all calls "
            "during the Phase 5C run. This script extracts structural "
            "features from the already-captured raw/governed pairs "
            "without re-introducing a judge or modifying source code."
        ),
        "n_pairs": len(rows),
        "raw_overall": agg(overall_raw),
        "governed_overall": agg(overall_gov),
        "by_category": {},
    }
    for cat, items in by_cat.items():
        raw_side = [a for a, _, _ in items]
        gov_side = [b for _, b, _ in items]
        out["by_category"][cat] = {
            "n": len(items),
            "raw": agg(raw_side),
            "governed": agg(gov_side),
        }

    # Selected illustrative deltas the paper can lean on.
    raw_overall = out["raw_overall"]
    gov_overall = out["governed_overall"]
    out["selected_deltas"] = {
        "ends_with_question_governed_minus_raw": round(
            gov_overall["ends_with_question_rate"] - raw_overall["ends_with_question_rate"], 4
        ),
        "mentions_verify_governed_minus_raw": round(
            gov_overall["mentions_verify_rate"] - raw_overall["mentions_verify_rate"], 4
        ),
        "mentions_freshness_governed_minus_raw": round(
            gov_overall["mentions_freshness_rate"] - raw_overall["mentions_freshness_rate"], 4
        ),
        "mean_length_chars_governed_minus_raw": round(
            gov_overall["mean_length_chars"] - raw_overall["mean_length_chars"], 1
        ),
    }
    # Special focus: ambiguous_underspecified ends-with-question delta.
    if "ambiguous_underspecified" in out["by_category"]:
        a = out["by_category"]["ambiguous_underspecified"]
        out["selected_deltas"]["ambiguous_ends_with_question_governed_minus_raw"] = round(
            a["governed"]["ends_with_question_rate"] - a["raw"]["ends_with_question_rate"], 4
        )

    out["caveats"] = [
        "Structural features only. NOT a judgment substitute.",
        "Does not measure correctness, restraint quality, or "
        "naturalness — those would require a judge.",
        "Identical raw text → identical features; this can't "
        "distinguish equally-shaped good and bad responses.",
        "Numbers are *suggestive* indicators of governance behavior "
        "(e.g., higher ends_with_question on ambiguous prompts is "
        "consistent with the appraisal layer asking back), but they "
        "are NOT a substitute for the missing judge.",
    ]

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"selected_deltas: {json.dumps(out['selected_deltas'], indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
