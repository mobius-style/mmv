"""Paired analysis for OPERATE-FR Smoke-100 (Raw vs MMV at 3 tiers).

Since Raw and MMV are evaluated on the *same 100 questions*, the right
test is paired:
  - 2x2 contingency per pair (a/b/c/d)
  - McNemar test on discordant pairs (continuity-corrected χ² + exact
    two-sided binomial test on b vs c)
  - Paired bootstrap 95% CI for the accuracy difference

Reports both:
  - rate          (classified_route ∈ allowed_routes)   — looser metric
  - preferred     (classified_route == preferred_route) — stricter metric

Output: Markdown to stdout (and an optional --out file).
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABELS = REPO / "operate-fr-bench" / "data" / "labels" / "smoke100_route_labels.jsonl"

PAIRS = [
    ("Small (qwen3.5:9b)",   "open_weight_local_9b_no_tool",                    "mmv_small_rc3_3_stabilized"),
    ("Medium (gemma4:26b)",  "raw_gemma4_26b_no_tool",                          "gemma4_26b_route_transformer_plus_validator_v3_1"),
    ("Large (gpt-oss-120b)", "cloud_reference_no_tool",                         "120b_route_transformer_plus_validator_v3_1"),
]

FAMS = ["stable_control", "date_boundary", "query_neutrality",
        "stale_premise_trap", "volatile_current", "ambiguous_time_frame"]


def _load_jsonl(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r["task_id"]] = r
    return out


def _correctness(row: dict, label: dict) -> tuple[bool, bool]:
    """Return (rate_correct, preferred_correct) for one row vs its label."""
    route = row.get("classified_route")
    rate = route in (label.get("allowed_routes") or [])
    pref = route == label.get("preferred_route")
    return rate, pref


# ── McNemar test (continuity-corrected χ² + exact two-sided binomial) ──

def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _chi2_1df_sf(stat: float) -> float:
    """Survival function (1 - CDF) for χ² with 1 dof.
    Closed form: P(χ²_1 > stat) = 2 * (1 - Φ(√stat))."""
    if stat < 0:
        return 1.0
    return 2.0 * (1.0 - _normal_cdf(math.sqrt(stat)))


def _binom_pmf(k: int, n: int, p: float = 0.5) -> float:
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def _binom_two_sided_exact(b: int, c: int) -> float:
    """Exact two-sided binomial p-value, H0: P(MMV beats Raw | discordant)=0.5.

    Uses the 'doubled smaller tail' definition.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # P(X <= k) under Bin(n, 0.5)
    tail = sum(_binom_pmf(i, n) for i in range(k + 1))
    return min(1.0, 2.0 * tail)


def mcnemar(b: int, c: int) -> dict:
    """Returns dict with χ²_cc, p_chi2, p_exact_binomial."""
    n = b + c
    if n == 0:
        return {"chi2_cc": 0.0, "p_chi2": 1.0, "p_exact": 1.0, "discordant": 0}
    chi2_cc = (abs(b - c) - 1) ** 2 / n if n > 0 else 0.0
    chi2_cc = max(0.0, chi2_cc)
    return {
        "chi2_cc": chi2_cc,
        "p_chi2": _chi2_1df_sf(chi2_cc),
        "p_exact": _binom_two_sided_exact(b, c),
        "discordant": n,
    }


def paired_bootstrap_ci(
    raw_correct: list[int], mmv_correct: list[int],
    n_boot: int = 10000, alpha: float = 0.05, seed: int = 42,
) -> tuple[float, float]:
    """95% CI for the mean of (mmv - raw) using paired bootstrap."""
    assert len(raw_correct) == len(mmv_correct)
    n = len(raw_correct)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        d = sum(mmv_correct[i] - raw_correct[i] for i in idx) / n
        diffs.append(d)
    diffs.sort()
    lo = diffs[int(alpha / 2 * n_boot)]
    hi = diffs[int((1 - alpha / 2) * n_boot) - 1]
    return (lo, hi)


# ── per-pair analysis ───────────────────────────────────────────────────

def analyze_pair(labels: dict, raw_rows: dict, mmv_rows: dict,
                 metric: str = "rate", subset: set[str] | None = None) -> dict:
    """Return contingency + McNemar + bootstrap for one metric.

    metric ∈ {"rate", "preferred"}
    subset: optional set of task_ids to restrict to (e.g. per-family).
    """
    common = set(raw_rows) & set(mmv_rows) & set(labels)
    if subset is not None:
        common &= subset

    raw_c, mmv_c = [], []
    a = b = c = d = 0
    for tid in sorted(common):
        lab = labels[tid]
        r_rate, r_pref = _correctness(raw_rows[tid], lab)
        m_rate, m_pref = _correctness(mmv_rows[tid], lab)
        r_ok = (r_pref if metric == "preferred" else r_rate)
        m_ok = (m_pref if metric == "preferred" else m_rate)
        raw_c.append(int(r_ok))
        mmv_c.append(int(m_ok))
        if r_ok and m_ok: a += 1
        elif r_ok and not m_ok: b += 1
        elif not r_ok and m_ok: c += 1
        else: d += 1

    n = len(raw_c)
    raw_acc = sum(raw_c) / n if n else 0.0
    mmv_acc = sum(mmv_c) / n if n else 0.0
    delta = mmv_acc - raw_acc
    mc = mcnemar(b, c)
    ci_lo, ci_hi = paired_bootstrap_ci(raw_c, mmv_c)
    return {
        "n": n,
        "raw_acc": raw_acc, "mmv_acc": mmv_acc, "delta": delta,
        "a": a, "b": b, "c": c, "d": d,
        "chi2_cc": mc["chi2_cc"], "p_chi2": mc["p_chi2"],
        "p_exact": mc["p_exact"], "discordant": mc["discordant"],
        "ci_lo": ci_lo, "ci_hi": ci_hi,
    }


def _fmt_p(p: float) -> str:
    if p < 0.001: return "<.001"
    if p < 0.01:  return f"{p:.3f}"
    return f"{p:.3f}"


def _sig(p: float) -> str:
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.10:  return "·"
    return ""


def render_report(reports_dir: Path) -> str:
    labels = _load_jsonl(LABELS)
    fam_subsets = defaultdict(set)
    # family is in label-side via failure_modes_to_check, but the family
    # label is in results' metadata. We'll pull it from the MMV results
    # (Raw should be the same family per task).
    # For now we'll build family-subsets when looking up each pair.

    L = []
    L.append("# OPERATE-FR Smoke-100 — Paired Analysis (Raw vs MMV at 3 tiers)")
    L.append("")
    L.append("Same 100 questions evaluated under both Raw and MMV for each "
             "tier (S/M/L). Each table cell reports the **2×2 contingency** "
             "(a/b/c/d) and a **McNemar test** on the discordant pairs:")
    L.append("")
    L.append("- **a** = both correct")
    L.append("- **b** = Raw correct / MMV wrong")
    L.append("- **c** = Raw wrong / MMV correct")
    L.append("- **d** = both wrong")
    L.append("")
    L.append("Discordant pairs **b + c** are the test's information; "
             "the null hypothesis is *P(MMV wins discordant | discordant) = 0.5*. "
             "We report both the **continuity-corrected χ² p-value** and the "
             "**exact two-sided binomial p-value** (the latter is preferred "
             "when b + c < 25). A **paired bootstrap 95% CI** on the "
             "accuracy difference (10,000 resamples, seed=42) is also reported.")
    L.append("")
    L.append("Significance: `***` p < .001, `**` p < .01, `*` p < .05, `·` p < .10.")
    L.append("")
    L.append("Two metrics:")
    L.append("- **rate**: `classified_route ∈ allowed_routes` (loose)")
    L.append("- **preferred**: `classified_route == preferred_route` (strict)")
    L.append("")

    pair_results = []  # (label, raw_rows, mmv_rows, overall_rate, overall_pref, fam_results)
    for label, raw_name, mmv_name in PAIRS:
        raw_rows = _load_jsonl(reports_dir / f"{raw_name}.jsonl")
        mmv_rows = _load_jsonl(reports_dir / f"{mmv_name}.jsonl")
        overall_rate = analyze_pair(labels, raw_rows, mmv_rows, "rate")
        overall_pref = analyze_pair(labels, raw_rows, mmv_rows, "preferred")

        # build family subsets (using MMV rows' metadata.family)
        fam_subsets = {f: set() for f in FAMS}
        for tid, row in mmv_rows.items():
            fam = ((row.get("metadata") or {}).get("family"))
            if fam in fam_subsets:
                fam_subsets[fam].add(tid)

        fam_results = {}
        for fam in FAMS:
            subset = fam_subsets[fam]
            if not subset:
                continue
            fam_results[fam] = {
                "rate": analyze_pair(labels, raw_rows, mmv_rows, "rate", subset),
                "pref": analyze_pair(labels, raw_rows, mmv_rows, "preferred", subset),
            }
        pair_results.append((label, raw_name, mmv_name, overall_rate, overall_pref, fam_results))

    # ── Overall headline (rate) ──
    L.append("## 1. Overall (rate) — paired contingency + McNemar")
    L.append("")
    L.append("| Pair | n | a | b (raw✓/mmv✗) | c (raw✗/mmv✓) | d | Raw acc | MMV acc | Δ | bootstrap 95% CI | McNemar χ²(cc) | p (χ²) | p (exact) | |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|")
    for label, _, _, o, _, _ in pair_results:
        sig = _sig(min(o["p_chi2"], o["p_exact"]))
        L.append(
            f"| **{label}** | {o['n']} | {o['a']} | {o['b']} | {o['c']} | {o['d']} | "
            f"{o['raw_acc']*100:.1f}% | {o['mmv_acc']*100:.1f}% | "
            f"{o['delta']*100:+.1f}pp | [{o['ci_lo']*100:+.1f}pp, {o['ci_hi']*100:+.1f}pp] | "
            f"{o['chi2_cc']:.2f} | {_fmt_p(o['p_chi2'])} | {_fmt_p(o['p_exact'])} | {sig} |"
        )
    L.append("")

    # ── Overall headline (preferred) ──
    L.append("## 2. Overall (preferred) — paired contingency + McNemar")
    L.append("")
    L.append("| Pair | n | a | b (raw✓/mmv✗) | c (raw✗/mmv✓) | d | Raw acc | MMV acc | Δ | bootstrap 95% CI | McNemar χ²(cc) | p (χ²) | p (exact) | |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|")
    for label, _, _, _, o, _ in pair_results:
        sig = _sig(min(o["p_chi2"], o["p_exact"]))
        L.append(
            f"| **{label}** | {o['n']} | {o['a']} | {o['b']} | {o['c']} | {o['d']} | "
            f"{o['raw_acc']*100:.1f}% | {o['mmv_acc']*100:.1f}% | "
            f"{o['delta']*100:+.1f}pp | [{o['ci_lo']*100:+.1f}pp, {o['ci_hi']*100:+.1f}pp] | "
            f"{o['chi2_cc']:.2f} | {_fmt_p(o['p_chi2'])} | {_fmt_p(o['p_exact'])} | {sig} |"
        )
    L.append("")

    # ── Per-family per-pair (rate) ──
    L.append("## 3. Per-family — paired contingency + McNemar (rate metric)")
    L.append("")
    for label, _, _, _, _, fr in pair_results:
        L.append(f"### {label}")
        L.append("")
        L.append("| Family | n | a | b | c | d | Raw | MMV | Δ | bootstrap 95% CI | p (exact) | |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|")
        for fam in FAMS:
            if fam not in fr:
                continue
            r = fr[fam]["rate"]
            sig = _sig(r["p_exact"])
            L.append(
                f"| {fam} | {r['n']} | {r['a']} | {r['b']} | {r['c']} | {r['d']} | "
                f"{r['raw_acc']*100:.0f}% | {r['mmv_acc']*100:.0f}% | "
                f"{r['delta']*100:+.0f}pp | [{r['ci_lo']*100:+.0f}pp, {r['ci_hi']*100:+.0f}pp] | "
                f"{_fmt_p(r['p_exact'])} | {sig} |"
            )
        L.append("")

    # ── Per-family per-pair (preferred) ──
    L.append("## 4. Per-family — paired contingency + McNemar (preferred metric)")
    L.append("")
    for label, _, _, _, _, fr in pair_results:
        L.append(f"### {label}")
        L.append("")
        L.append("| Family | n | a | b | c | d | Raw | MMV | Δ | bootstrap 95% CI | p (exact) | |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|")
        for fam in FAMS:
            if fam not in fr:
                continue
            r = fr[fam]["pref"]
            sig = _sig(r["p_exact"])
            L.append(
                f"| {fam} | {r['n']} | {r['a']} | {r['b']} | {r['c']} | {r['d']} | "
                f"{r['raw_acc']*100:.0f}% | {r['mmv_acc']*100:.0f}% | "
                f"{r['delta']*100:+.0f}pp | [{r['ci_lo']*100:+.0f}pp, {r['ci_hi']*100:+.0f}pp] | "
                f"{_fmt_p(r['p_exact'])} | {sig} |"
            )
        L.append("")

    L.append("---")
    L.append("")
    L.append("## Reading notes")
    L.append("")
    L.append("- Marginal accuracy (Raw acc, MMV acc) matches the unpaired summary; "
             "the **value of pairing is in the test, not in the point estimate**.")
    L.append("- For small discordant counts (b+c < 25), trust the **exact binomial p** over χ² — "
             "the continuity-corrected χ² over-rejects on small cells.")
    L.append("- A **non-significant** Δ with a wide CI just means we lack power at n=100; "
             "it does NOT mean the governance had no effect. Larger smoke (n=300–500) "
             "is needed to detect ≤5pp differences reliably.")
    L.append("- Per-family tests have very small n (3–35). Family-level p-values are "
             "**directional indicators only**, not confirmatory tests. The headline overall "
             "test is the load-bearing claim.")
    L.append("- McNemar is one-tailed in its null structure (b vs c) but we report the "
             "two-sided p as the default since we don't pre-register direction.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", type=str,
                    default=str(REPO / "operate-fr-bench" / "reports"))
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    md = render_report(Path(args.reports_dir))
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote → {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
