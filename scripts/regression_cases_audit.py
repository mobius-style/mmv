"""B. Regression case audit — dump every b-case (Raw correct, MMV wrong) for T to read.

A b-case is a question where:
  - Raw's classified_route ∈ allowed_routes  (raw passes)
  - MMV's classified_route ∉ allowed_routes (mmv fails)

This is pure governance cost — the kernel intervened on a case that Raw already had right.

For each b-case the report emits the full context (prompt, label, both
classified_routes, full response texts) so the human reviewer can
classify the failure mode into:
  - over_reanchor
  - unnecessary_ask
  - missed_stable_control
  - date_bound_over_insertion
  - validator_false_positive
  - other (free text)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABELS = REPO / "operate-fr-bench" / "data" / "labels" / "smoke100_route_labels.jsonl"

PAIRS = [
    ("Small (qwen3.5:9b)",
     "open_weight_local_9b_no_tool",
     "mmv_small_rc3_3_stabilized"),
    ("Medium (gemma4:26b)",
     "raw_gemma4_26b_no_tool",
     "gemma4_26b_route_transformer_plus_validator_v3_1"),
    ("Large (gpt-oss-120b)",
     "cloud_reference_no_tool",
     "120b_route_transformer_plus_validator_v3_1"),
]


def _load_jsonl(path: Path) -> dict[str, dict]:
    out = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r["task_id"]] = r
    return out


def _prompt_text(row: dict) -> str:
    # OPERATE-FR run_eval stores the user prompt in `user_prompt`
    # (preferred) or falls back to the run's task `prompt`.
    return (row.get("user_prompt") or row.get("prompt")
            or "(prompt not captured)")


def _resp_text(row: dict) -> str:
    return (row.get("response_text") or row.get("response_raw")
            or row.get("response") or "(no response captured)")


def _meta(row: dict) -> dict:
    return row.get("metadata") or {}


def _render_pair_audit(label: str, raw: dict, mmv: dict,
                        labels: dict) -> list[str]:
    L = []
    L.append(f"## {label}")
    L.append("")

    b_cases = []
    for tid in sorted(set(raw) & set(mmv) & set(labels)):
        lab = labels[tid]
        allowed = lab.get("allowed_routes") or []
        r_route = raw[tid].get("classified_route")
        m_route = mmv[tid].get("classified_route")
        if r_route in allowed and m_route not in allowed:
            b_cases.append((tid, lab, raw[tid], mmv[tid]))

    L.append(f"**Total b-cases (Raw ✓ / MMV ✗): {len(b_cases)}**")
    L.append("")

    if not b_cases:
        L.append("_None — governance applied zero unforced costs on this pair._")
        L.append("")
        return L

    L.append("| task_id | family | Raw route | MMV route | allowed_routes | preferred |")
    L.append("|---|---|---|---|---|---|")
    for tid, lab, rrow, mrow in b_cases:
        fam = _meta(mrow).get("family", "?")
        r_route = rrow.get("classified_route", "?")
        m_route = mrow.get("classified_route", "?")
        L.append(f"| `{tid}` | {fam} | `{r_route}` | **`{m_route}`** | "
                 f"{','.join(lab.get('allowed_routes') or [])} | "
                 f"`{lab.get('preferred_route','?')}` |")
    L.append("")

    for tid, lab, rrow, mrow in b_cases:
        fam = _meta(mrow).get("family", "?")
        L.append(f"### `{tid}` — family={fam}")
        L.append("")
        L.append(f"- **Raw route**: `{rrow.get('classified_route')}` (in allowed)")
        L.append(f"- **MMV route**: `{mrow.get('classified_route')}` ❌ (outside allowed)")
        L.append(f"- **allowed_routes**: `{lab.get('allowed_routes')}`")
        L.append(f"- **preferred_route**: `{lab.get('preferred_route')}`")
        L.append(f"- **route_notes**: {lab.get('route_notes', '—')}")
        rt_inj = _meta(mrow).get("route_transformer_injected")
        rt_fam = _meta(mrow).get("route_transformer_family")
        pv_rew = _meta(mrow).get("post_validator_rewritten")
        pv_notes = _meta(mrow).get("post_validator_notes")
        if rt_inj is not None or pv_rew is not None:
            L.append(f"- **harness audit**: route_transformer_injected={rt_inj}"
                     f" (family={rt_fam}), post_validator_rewritten={pv_rew}, "
                     f"post_validator_notes={pv_notes}")
        L.append("")

        prompt = _prompt_text(mrow)
        L.append("**Prompt** (≤500 chars):")
        L.append("")
        L.append("```")
        L.append(prompt[:500])
        if len(prompt) > 500:
            L.append("…(truncated)")
        L.append("```")
        L.append("")

        L.append("**Raw response** (≤600 chars):")
        L.append("")
        L.append("```")
        rtxt = _resp_text(rrow)
        L.append(rtxt[:600])
        if len(rtxt) > 600:
            L.append("…(truncated)")
        L.append("```")
        L.append("")

        L.append("**MMV response** (≤600 chars):")
        L.append("")
        L.append("```")
        mtxt = _resp_text(mrow)
        L.append(mtxt[:600])
        if len(mtxt) > 600:
            L.append("…(truncated)")
        L.append("```")
        L.append("")

        L.append("**Failure mode classification** (fill in):")
        L.append("- [ ] over_reanchor — kernel re-anchored a premise that wasn't actually stale")
        L.append("- [ ] unnecessary_ask — kernel asked when Raw could have answered")
        L.append("- [ ] missed_stable_control — kernel hedged a stable fact")
        L.append("- [ ] date_bound_over_insertion — kernel added a date-bound on a non-volatile item")
        L.append("- [ ] validator_false_positive — post-validator rewrote a correct answer into an incorrect form")
        L.append("- [ ] other: _____________")
        L.append("")
        L.append("**Notes**: _____________")
        L.append("")
        L.append("---")
        L.append("")

    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", type=str,
                    default=str(REPO / "operate-fr-bench" / "reports"))
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    reports = Path(args.reports_dir)
    labels = _load_jsonl(LABELS)

    L = []
    L.append("# OPERATE-FR Smoke-100 — Regression Case Audit (b-cases)")
    L.append("")
    L.append("Every question where **Raw produced an allowed route but MMV produced "
             "a disallowed route** is dumped below with full context. This is the "
             "*governance cost* — quote of cases the kernel got wrong that Raw got "
             "right. Use the failure-mode classification at the end of each entry "
             "to characterize the cost.")
    L.append("")
    L.append("**Failure mode taxonomy** (from spec):")
    L.append("- `over_reanchor` — kernel re-anchored a premise that wasn't actually stale")
    L.append("- `unnecessary_ask` — kernel asked a clarifying question when Raw could have answered")
    L.append("- `missed_stable_control` — kernel hedged a stable factual control")
    L.append("- `date_bound_over_insertion` — kernel added a date-boundary hedge on a non-volatile item")
    L.append("- `validator_false_positive` — post-validator rewrote a correct answer into an incorrect form")
    L.append("")

    for label, raw_name, mmv_name in PAIRS:
        raw = _load_jsonl(reports / f"{raw_name}.jsonl")
        mmv = _load_jsonl(reports / f"{mmv_name}.jsonl")
        L.extend(_render_pair_audit(label, raw, mmv, labels))

    md = "\n".join(L)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote → {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
