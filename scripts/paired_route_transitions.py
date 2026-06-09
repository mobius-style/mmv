"""A. Per-pair route transition matrix (Raw route → MMV route) for OPERATE-FR Smoke-100.

For each tier (Small/Medium/Large), emits:
  - One overall transition matrix (rows=Raw route, cols=MMV route)
  - Per-family transition tables with allowed-route-based annotation:
      ↑  c-case (Raw outside allowed_routes, MMV inside)  — recovery
      ↓  b-case (Raw inside allowed_routes, MMV outside)  — regression
      ✓  both inside (concordant pass)
      ·  both outside (concordant fail)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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

ROUTES = ["answer", "date_bound_answer", "verify", "re_anchor",
          "ask", "abstain", "execute"]

FAMS = ["stable_control", "date_boundary", "query_neutrality",
        "stale_premise_trap", "volatile_current", "ambiguous_time_frame"]


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


def _build_overall_matrix(raw: dict, mmv: dict) -> Counter:
    mat = Counter()
    for tid in set(raw) & set(mmv):
        r = raw[tid].get("classified_route", "?")
        m = mmv[tid].get("classified_route", "?")
        mat[(r, m)] += 1
    return mat


def _annotate(raw_route: str, mmv_route: str, allowed: list) -> str:
    rin = raw_route in allowed
    min_ = mmv_route in allowed
    if rin and min_:   return "✓"   # both pass
    if not rin and not min_: return "·"  # both fail
    if not rin and min_:     return "↑"  # recovery (c)
    return "↓"   # regression (b)


def _matrix_md(mat: Counter, routes_used: list[str], label: str = "") -> list[str]:
    L = []
    L.append(f"| {label} → MMV | " + " | ".join(routes_used) + " | Σ raw |")
    L.append("|---|" + "|".join(["---:"] * (len(routes_used) + 1)) + "|")
    raw_routes = sorted({r for r, _ in mat.keys()},
                        key=lambda x: routes_used.index(x) if x in routes_used else 99)
    for r in raw_routes:
        cells = []
        rsum = 0
        for m in routes_used:
            v = mat.get((r, m), 0)
            cells.append(str(v) if v else "·")
            rsum += v
        L.append(f"| **{r}** | " + " | ".join(cells) + f" | **{rsum}** |")
    csum = [sum(v for (rr, mm), v in mat.items() if mm == m) for m in routes_used]
    L.append(f"| **Σ mmv** | " + " | ".join(f"**{c}**" if c else "·" for c in csum)
             + f" | **{sum(mat.values())}** |")
    return L


def _render_pair(label: str, raw: dict, mmv: dict, labels: dict) -> list[str]:
    L = []
    L.append(f"## {label}")
    L.append("")

    # routes that actually appear in either column, in fixed order
    used = set()
    for (r, m) in _build_overall_matrix(raw, mmv).keys():
        used.add(r); used.add(m)
    routes_used = [r for r in ROUTES if r in used]

    # ── overall transition matrix ──
    L.append("### Overall transition matrix (Raw route → MMV route)")
    L.append("")
    mat = _build_overall_matrix(raw, mmv)
    L.extend(_matrix_md(mat, routes_used, label="Raw"))
    L.append("")

    # ── per-family transition list with annotation ──
    L.append("### Per-family transitions (with allowed-route annotation)")
    L.append("")
    L.append("Legend: ✓ both routes in allowed_routes (pass) · "
             "**↑** Raw fail → MMV pass (recovery, c-case) · "
             "**↓** Raw pass → MMV fail (regression, b-case) · "
             "· both fail")
    L.append("")
    L.append("| Family (n) | Transition | Count | Annotation |")
    L.append("|---|---|---:|:---:|")
    # Build per-family transition counts using MMV metadata.family + labels.allowed_routes
    fam_to_mat: dict[str, Counter] = defaultdict(Counter)
    fam_to_allowed: dict[str, list] = defaultdict(list)
    for tid in set(raw) & set(mmv) & set(labels):
        fam = ((mmv[tid].get("metadata") or {}).get("family") or "?")
        if fam not in FAMS:
            continue
        r = raw[tid].get("classified_route", "?")
        m = mmv[tid].get("classified_route", "?")
        fam_to_mat[fam][(r, m)] += 1
        if not fam_to_allowed[fam]:
            fam_to_allowed[fam] = labels[tid].get("allowed_routes", [])

    for fam in FAMS:
        if fam not in fam_to_mat:
            continue
        allowed = fam_to_allowed[fam]
        n = sum(fam_to_mat[fam].values())
        rows = sorted(fam_to_mat[fam].items(),
                      key=lambda kv: (-kv[1], kv[0]))
        first = True
        for (r, m), v in rows:
            ann = _annotate(r, m, allowed)
            fam_cell = f"**{fam}** (n={n})\nallowed={','.join(allowed) or '—'}" if first else ""
            first = False
            arrow = "→"
            L.append(f"| {fam_cell} | `{r}` {arrow} `{m}` | {v} | {ann} |")
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
    L.append("# OPERATE-FR Smoke-100 — Paired Route Transitions (Raw → MMV)")
    L.append("")
    L.append("For each (Raw, MMV) profile pair on the same 100 questions, "
             "this report counts the *epistemic act transitions*: how many "
             "Raw `route_X` answers became MMV `route_Y` answers. Per-family "
             "rows additionally annotate each transition against the family's "
             "`allowed_routes` set, so you can see whether the conversion is "
             "a recovery (↑), regression (↓), or concordant (✓ / ·).")
    L.append("")

    for label, raw_name, mmv_name in PAIRS:
        raw = _load_jsonl(reports / f"{raw_name}.jsonl")
        mmv = _load_jsonl(reports / f"{mmv_name}.jsonl")
        L.extend(_render_pair(label, raw, mmv, labels))

    L.append("---")
    L.append("")
    L.append("## How to read")
    L.append("")
    L.append("- The overall matrix shows the gross epistemic shift the "
             "governance layer applies. Concentrate on **off-diagonal cells** "
             "— those are the conversions.")
    L.append("- In the per-family list, the **↑ rows are governance wins** — "
             "the kernel correctly intervened on a Raw error. The **↓ rows are "
             "governance costs** — the kernel intervened where Raw was already "
             "right. ↓ rows feed directly into the regression-case audit "
             "(`operate_fr_smoke100_regression_cases.md`).")
    L.append("- `✓` rows are no-op concordant passes; `·` rows are no-op "
             "concordant fails (model & kernel agreed the answer was hard).")
    L.append("- A high concentration of `answer → date_bound_answer` on "
             "`volatile_current` is the *designed* RC3.3 v3.1 behaviour. "
             "A high concentration of `answer → re_anchor` on "
             "`stale_premise_trap` is the *designed* force_reanchor_v2 behaviour. "
             "Anything else is worth a second look.")

    md = "\n".join(L)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote → {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
