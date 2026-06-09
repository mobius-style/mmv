#!/usr/bin/env python3
"""Build smoke input for v0.1-rc2 route-calibration patch.

Sample composition (deterministic seed 20260429):
  specialized_terminology     20  (direct-answer; expect improvement)
  conceptual_explanation      20  (direct-answer; expect improvement)
  casual_smalltalk            10  (direct-answer; expect no regression)
  ambiguous_underspecified    20  (restraint; regression guard)
  continuation                20  (restraint; regression guard)
  factual_inquiry             20  (mixed; freshness regression guard)

Total: 110 queries. All sourced from
`eval/p9_evidence_pack_v1/holdout_english_longtail_v1.jsonl`. Output:
  smoke_input.jsonl
"""
import json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOLDOUT = ROOT.parent.parent / "eval/p9_evidence_pack_v1/holdout_english_longtail_v1.jsonl"
OUT = ROOT / "smoke_input.jsonl"

PER_CAT = {
    "specialized_terminology":  20,
    "conceptual_explanation":   20,
    "casual_smalltalk":         10,
    "ambiguous_underspecified": 20,
    "continuation":             20,
    "factual_inquiry":          20,
}

by_cat = {}
for line in HOLDOUT.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    by_cat.setdefault(obj["category"], []).append(obj)

rng = random.Random(20260429)
out = []
for cat, n in PER_CAT.items():
    pool = list(by_cat.get(cat, []))
    rng.shuffle(pool)
    out.extend(pool[:n])

OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
               encoding="utf-8")
print(f"wrote {len(out)} → {OUT}")
counts = {}
for r in out:
    counts[r["category"]] = counts.get(r["category"], 0) + 1
print(f"per-category: {counts}")
