#!/usr/bin/env python3
"""Phase 5F Cell B — Common-sense + retrieval contamination (n=20).

20 hand-authored common-sense factual queries across four domains
(physics / chemistry / biology / economics), 5 each. These are
questions a reasonable model can answer from general knowledge
without retrieval — but MMV's Pattern Library may trigger Box W
retrieval, and Box W FAISS may return an off-topic article. The
question is: when retrieval misses, does the response *contaminate*
itself with off-topic concepts from the retrieved chunk?

Cell B runs RC2 governed only (no raw comparison; raw is out of
scope per the prompt — contamination signature is the goal).

Manual-review contamination judgment criteria (recorded in summary):
  off_topic_concept     — response cites or paraphrases a concept
                           that is clearly from a retrieved off-
                           topic article and is irrelevant to the
                           query (e.g., "Rayleigh length" in a
                           sky-color answer).
  wrong_context_fact    — a correct fact applied to the wrong
                           context (e.g., chemistry fact in a
                           physics question).
  spurious_framework    — mentions a framework, protocol, or
                           proper-noun system that has no relation
                           to the query.

Manual judgment is recorded as a separate JSON written by the
operator (not by this script). This script captures the data and
applies an automated heuristic flag for triage.

Output: data/phase5f/common_sense_contamination_n20.jsonl
"""
from __future__ import annotations

import json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

DATA_DIR = ROOT / "data" / "phase5f"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT = DATA_DIR / "common_sense_contamination_n20.jsonl"

WIKI_HIT_THRESHOLD = 0.75

# Hand-authored common-sense questions (5 per domain, 20 total).
# Each has a `domain`, the natural-knowledge `gold_topic` (a canonical
# concept the answer should mention), and a list of `contamination_seed_terms`
# — phrases that, if they appear in the answer without context, are
# strong heuristic signals of retrieval contamination from an
# unrelated article. These seeds were picked from known-off-topic
# Wikipedia articles in adjacent topical neighborhoods.
QUERIES = [
    # ── Physics ─────────────────────────────────────────────
    {"id": "csb_phys_01", "domain": "physics_optics",
     "query": "Why is the sky blue during the day?",
     "gold_topic": "Rayleigh scattering",
     "contamination_seed_terms": ["Rayleigh length", "Rayleigh range", "laser beam waist", "Gaussian beam"]},
    {"id": "csb_phys_02", "domain": "physics_optics",
     "query": "Why do rainbows form after rain?",
     "gold_topic": "refraction and dispersion in water droplets",
     "contamination_seed_terms": ["chromatic aberration of lens", "fiber-optic dispersion", "prism spectrometer"]},
    {"id": "csb_phys_03", "domain": "physics_mechanics",
     "query": "Why does a feather fall slower than a rock in air?",
     "gold_topic": "air resistance / drag",
     "contamination_seed_terms": ["aerodynamic stability", "Mach number", "Bernoulli's principle"]},
    {"id": "csb_phys_04", "domain": "physics_thermo",
     "query": "Why does ice melt when you put salt on it?",
     "gold_topic": "freezing-point depression",
     "contamination_seed_terms": ["osmotic pressure", "boiling-point elevation", "salt-water electrolysis"]},
    {"id": "csb_phys_05", "domain": "physics_thermo",
     "query": "Why does hot air rise?",
     "gold_topic": "buoyancy / thermal convection",
     "contamination_seed_terms": ["Reynolds number", "boundary layer", "Coriolis force"]},
    # ── Chemistry ───────────────────────────────────────────
    {"id": "csb_chem_01", "domain": "chemistry",
     "query": "Why does iron rust over time?",
     "gold_topic": "oxidation in presence of water and oxygen",
     "contamination_seed_terms": ["galvanic corrosion of zinc", "passivation layer of aluminum", "stainless-steel chromium oxide"]},
    {"id": "csb_chem_02", "domain": "chemistry",
     "query": "Why does soap make water bubbly?",
     "gold_topic": "surfactants reduce surface tension",
     "contamination_seed_terms": ["micelle phase separation", "lipid bilayer", "amphiphilic phospholipid"]},
    {"id": "csb_chem_03", "domain": "chemistry",
     "query": "Why does bread rise when you add yeast?",
     "gold_topic": "yeast produces carbon dioxide via fermentation",
     "contamination_seed_terms": ["alcohol distillation", "Saccharomyces cerevisiae genome", "anaerobic respiration in mitochondria"]},
    {"id": "csb_chem_04", "domain": "chemistry",
     "query": "Why does cut apple turn brown?",
     "gold_topic": "enzymatic browning / polyphenol oxidase",
     "contamination_seed_terms": ["Maillard reaction", "caramelization at 170C", "oxidative phosphorylation"]},
    {"id": "csb_chem_05", "domain": "chemistry",
     "query": "Why does vinegar react with baking soda?",
     "gold_topic": "acid-base reaction releasing carbon dioxide",
     "contamination_seed_terms": ["citric acid cycle", "Krebs cycle", "buffer solution titration"]},
    # ── Biology ─────────────────────────────────────────────
    {"id": "csb_bio_01", "domain": "biology",
     "query": "Why do leaves change color in autumn?",
     "gold_topic": "chlorophyll breakdown reveals carotenoids/anthocyanins",
     "contamination_seed_terms": ["photosystem II quantum yield", "phototropism", "C4 carbon fixation"]},
    {"id": "csb_bio_02", "domain": "biology",
     "query": "Why do we get hungry?",
     "gold_topic": "ghrelin and blood glucose regulation",
     "contamination_seed_terms": ["mitochondrial ATP synthesis", "Krebs cycle", "leptin obesity studies"]},
    {"id": "csb_bio_03", "domain": "biology",
     "query": "Why do cuts heal over time?",
     "gold_topic": "platelet clotting and tissue regeneration",
     "contamination_seed_terms": ["stem-cell differentiation pathway", "fibroblast collagen Type III", "angiogenesis VEGF"]},
    {"id": "csb_bio_04", "domain": "biology",
     "query": "Why do plants grow toward light?",
     "gold_topic": "phototropism / auxin",
     "contamination_seed_terms": ["circadian rhythm CLOCK gene", "photosynthesis light reactions", "C3/C4 differentiation"]},
    {"id": "csb_bio_05", "domain": "biology",
     "query": "Why do we sweat when it's hot?",
     "gold_topic": "evaporative cooling / thermoregulation",
     "contamination_seed_terms": ["sodium-potassium pump", "aquaporin channel", "antidiuretic hormone vasopressin"]},
    # ── Economics / Finance ──────────────────────────────────
    {"id": "csb_econ_01", "domain": "economics",
     "query": "Why does inflation happen?",
     "gold_topic": "money supply growth and demand-pull",
     "contamination_seed_terms": ["Lucas critique", "Phillips curve flattening", "rational expectations equilibrium"]},
    {"id": "csb_econ_02", "domain": "economics",
     "query": "Why are houses more expensive in cities?",
     "gold_topic": "supply constraints + agglomeration demand",
     "contamination_seed_terms": ["central place theory", "von Thünen model", "Henry George tax"]},
    {"id": "csb_econ_03", "domain": "economics",
     "query": "Why do banks pay interest on savings?",
     "gold_topic": "compensation for use of capital + fractional reserve",
     "contamination_seed_terms": ["yield-curve inversion", "interbank LIBOR replacement", "Basel III liquidity ratio"]},
    {"id": "csb_econ_04", "domain": "economics",
     "query": "Why does the price of gold change?",
     "gold_topic": "supply, demand, and macro hedging behavior",
     "contamination_seed_terms": ["Bretton Woods system", "London Bullion Market Association fix", "COMEX futures basis"]},
    {"id": "csb_econ_05", "domain": "economics",
     "query": "Why do governments tax cigarettes more than vegetables?",
     "gold_topic": "Pigouvian externality correction + price elasticity",
     "contamination_seed_terms": ["Laffer curve", "Ramsey optimal taxation theorem", "capital gains step-up basis"]},
]


def call_governed_with_retrieval(query: str) -> tuple[str, dict]:
    from scripts.pseudo_ui_runner import PseudoUISession
    sess = PseudoUISession()
    t0 = time.time()
    try:
        r = sess.process_turn(query)
        text = r.response_text or ""
        bw = []
        for c in (r.box_w_top_chunks or [])[:5]:
            bw.append({
                "source_label": getattr(c, "source_label", ""),
                "chunk_index": getattr(c, "chunk_index", None),
                "relevance_score": float(getattr(c, "relevance_score", 0.0) or 0.0),
                "text_excerpt": (getattr(c, "text_excerpt", "") or "")[:200],
            })
        b0 = []
        for c in (r.box_0_top_chunks or [])[:5]:
            b0.append({
                "source_label": getattr(c, "source_label", ""),
                "chunk_index": getattr(c, "chunk_index", None),
                "relevance_score": float(getattr(c, "relevance_score", 0.0) or 0.0),
                "text_excerpt": (getattr(c, "text_excerpt", "") or "")[:200],
            })
        return (text, {
            "ok": True, "elapsed_s": round(time.time() - t0, 2),
            "route": r.route, "reason_codes": list(r.reason_codes or [])[:8],
            "intent_type": getattr(r, "intent_type", ""),
            "box_w_top_chunks": bw, "box_0_top_chunks": b0,
        })
    except Exception as e:
        return ("", {"ok": False, "elapsed_s": round(time.time() - t0, 2),
                     "error": f"{type(e).__name__}: {str(e)[:120]}"})


def auto_contamination_flag(query_meta: dict, governed_text: str) -> tuple[bool, list[str]]:
    """Heuristic contamination flag: did the response include any of
    the pre-listed contamination seed terms? Triages for manual
    review; manual judgment is authoritative."""
    if not governed_text:
        return (False, [])
    hits = []
    text_lower = governed_text.lower()
    for term in query_meta.get("contamination_seed_terms", []):
        if term.lower() in text_lower:
            hits.append(term)
    return (bool(hits), hits)


def main() -> int:
    rows = []
    n_retrieval_hit = 0
    n_auto_contamination = 0
    by_domain = {}
    t0 = time.time()
    for i, q in enumerate(QUERIES, 1):
        text, meta = call_governed_with_retrieval(q["query"])
        bw = meta.get("box_w_top_chunks", []) if meta.get("ok") else []
        retrieval_hit = any(
            (c.get("relevance_score") or 0.0) >= WIKI_HIT_THRESHOLD
            for c in bw
        )
        auto_flag, auto_terms = auto_contamination_flag(q, text)
        if retrieval_hit:
            n_retrieval_hit += 1
        if auto_flag:
            n_auto_contamination += 1
        bd = by_domain.setdefault(q["domain"], {"n": 0, "auto_contam": 0,
                                                "retrieval_hit": 0})
        bd["n"] += 1
        bd["auto_contam"] += int(auto_flag)
        bd["retrieval_hit"] += int(retrieval_hit)

        rows.append({
            "id": q["id"], "domain": q["domain"], "query": q["query"],
            "gold_topic": q["gold_topic"],
            "contamination_seed_terms": q["contamination_seed_terms"],
            "governed_response": text, "governed_meta": meta,
            "retrieval": {
                "box_w_top_chunks": bw,
                "box_0_top_chunks": meta.get("box_0_top_chunks", []) if meta.get("ok") else [],
                "retrieval_hit_box_w": retrieval_hit,
                "wiki_threshold": WIKI_HIT_THRESHOLD,
            },
            "contamination": {
                "automated_flag": auto_flag,
                "automated_seed_hits": auto_terms,
                "manual_review_required": True,  # all entries reviewed manually
                "manual_judgment": None,  # filled by operator
                "manual_type": None,      # off_topic_concept | wrong_context_fact | spurious_framework
            },
        })
        elapsed = time.time() - t0
        if i % 5 == 0 or i == len(QUERIES):
            print(f"  [{i}/{len(QUERIES)}] elapsed={elapsed:.1f}s "
                  f"retr_hit={n_retrieval_hit} auto_contam={n_auto_contamination}",
                  flush=True)

    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    # 95% Wilson CI for contamination rate
    import math
    n = len(rows)
    rate = n_auto_contamination / n if n else 0
    if n:
        z = 1.96; phat = rate; denom = 1 + z**2 / n
        center = phat + z**2 / (2 * n)
        rad = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))
        ci_lo = max(0.0, (center - rad) / denom)
        ci_hi = min(1.0, (center + rad) / denom)
    else:
        ci_lo = ci_hi = 0.0

    summary = {
        "test": "phase5f.cell_b.common_sense_contamination_n20",
        "n": n,
        "n_retrieval_hit_box_w": n_retrieval_hit,
        "n_auto_contamination": n_auto_contamination,
        "auto_contamination_rate": round(rate, 4),
        "auto_contamination_rate_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
        "retrieval_hit_rate_box_w": round(n_retrieval_hit / n, 4) if n else 0,
        "by_domain": by_domain,
        "elapsed_s": round(time.time() - t0, 1),
        "notes": (
            "Automated flag uses pre-listed contamination seed terms; "
            "MANUAL review by operator is authoritative for "
            "off_topic_concept / wrong_context_fact / "
            "spurious_framework classification."
        ),
    }
    (DATA_DIR / "_cell_b_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"\nwrote {OUT}")
    print(f"summary: {json.dumps(summary, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
