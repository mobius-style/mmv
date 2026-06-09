#!/usr/bin/env python3
"""Regenerate governed responses with v0.1-rc2 runtime.

Reuses the same 60 queries from Phase 5C Test 2; raw responses are
copied verbatim from the saved Phase 5C JSONL (NOT regenerated).
"""
import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
PHASE5C_PAIRS = ROOT / "eval/p9_evidence_pack_v1/raw_vs_governed_per_query.jsonl"
RC1_GROQ_JUDGE = ROOT / "eval/p9_evidence_pack_v1/raw_vs_governed_groq120b_judge_results.jsonl"
PAIRS_OUT = OUT_DIR / "raw_vs_rc2_governed_pairs.jsonl"


def main() -> int:
    from scripts.pseudo_ui_runner import PseudoUISession

    pairs_in = []
    for line in PHASE5C_PAIRS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        pairs_in.append(json.loads(line))
    print(f"loaded {len(pairs_in)} Phase 5C pairs", flush=True)

    # Optional: load saved rc1 Groq120B judge scores to enable
    # raw / rc1 / rc2 three-way comparison.
    rc1_judge = {}
    if RC1_GROQ_JUDGE.exists():
        for line in RC1_GROQ_JUDGE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rc1_judge[r["id"]] = {
                "rc1_governed_response_excerpt": r.get("governed_response_excerpt", ""),
                "rc1_judge": r.get("judge", {}),
                "rc1_judge_meta": r.get("judge_meta", {}),
                "rc1_a_was_governed": r.get("a_was_governed"),
                "rc1_raw_total_20": r.get("raw_total_20"),
                "rc1_governed_total_20": r.get("governed_total_20"),
                "rc1_winner_label": r.get("winner_label"),
            }
    print(f"rc1 Groq120B judge rows available: {len(rc1_judge)}", flush=True)

    rows = []
    t0 = time.time()
    for i, p in enumerate(pairs_in, 1):
        sess = PseudoUISession()
        try:
            r = sess.process_turn(p["query"])
            rc2_governed = r.response_text or ""
            rc2_meta = {
                "route": r.route,
                "reason_codes": list(r.reason_codes or [])[:8],
                "intent_type": getattr(r, "intent_type", ""),
                "ok": True,
            }
        except Exception as e:
            rc2_governed = ""
            rc2_meta = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}

        row = {
            "id": p["id"],
            "category": p["category"],
            "query": p["query"],
            "expected_route": p.get("expected_route"),
            "raw_response": p["raw_response"],          # reused, NOT regenerated
            "raw_meta": p.get("raw_meta", {}),          # reused
            "rc1_governed_response": p.get("governed_response", ""),
            "rc1_governed_meta": p.get("governed_meta", {}),
            "rc2_governed_response": rc2_governed,
            "rc2_governed_meta": rc2_meta,
        }
        rj = rc1_judge.get(p["id"])
        if rj:
            row.update(rj)
        rows.append(row)

        if i % 5 == 0 or i == len(pairs_in):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(pairs_in)}] elapsed={elapsed:.1f}s", flush=True)

    PAIRS_OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {PAIRS_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
