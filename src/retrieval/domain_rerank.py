#!/usr/bin/env python3
"""
domain_rerank.py — Phase G.12: Box W post-retrieval domain-aware boost.

The existing Wiki FAISS index returns top-k sources by cosine similarity.
For short technical queries in a known domain (e.g. "counit" in
category theory), the top hit can drift toward a surface-lexical
neighbor in a different domain (counter/electronics). Post-G.11 the
reformulator already appends a domain anchor to `en_keywords`; this
module adds a bounded *post-retrieval* reranker that nudges results
whose title/label/text mentions the domain anchor terms.

Principles:
  - no index-side changes (backend architecture untouched)
  - no giant ontology
  - pure function: (sources, synthesis, domain_hint) → reranked (sources, synthesis, notes)
  - conservative: only reorders; never invents new sources, never drops
    sources, never changes scores by more than a small bounded delta
  - inspectable: returns a notes list with domain_boost events

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


# Boost magnitudes. Small and bounded so that genuinely-relevant hits
# (high cosine) win even without a domain match; the boost breaks ties
# between otherwise similar results by domain alignment.
DOMAIN_BOOST_TITLE_HIT    = 0.08   # domain keyword appears in title/label
DOMAIN_BOOST_BODY_HIT     = 0.04   # domain keyword appears in snippet/body
DOMAIN_BOOST_MAX_TOTAL    = 0.15   # cap so boosts cannot dominate raw score


# Compact keyword expansion per canonical domain. Keep each list short
# and focused; these are discriminators, not topic models.
_DOMAIN_KEYWORDS: dict[str, List[str]] = {
    "category theory": [
        "category theory", "categorical", "morphism", "functor",
        "monad", "adjoint", "kleisli", "eilenberg", "monoidal",
        "homological", "cohomolog",
    ],
    "linear algebra": [
        "linear algebra", "vector space", "eigen", "matrix",
        "matrices", "determinant", "orthogonal", "jordan form",
    ],
    "tensor mathematics": [
        "tensor", "tensor field", "multilinear", "ricci", "metric",
    ],
    "multivariable calculus": [
        "calculus", "gradient", "jacobian", "hessian", "manifold",
    ],
    "Lie theory": [
        "lie algebra", "lie group", "lie bracket", "exponential map",
        "root system",
    ],
    "abstract algebra": [
        "group theory", "group action", "homomorphism", "ring", "field",
        "module", "galois",
    ],
    "topology": [
        "topology", "topological", "open set", "compact", "connected",
        "homeomorph",
    ],
    "algebraic topology": [
        "homology", "cohomology", "fundamental group", "covering space",
        "chain complex",
    ],
    "quantum mechanics": [
        "quantum", "wave function", "schrödinger", "schrodinger",
        "hilbert space", "operator", "observable", "entanglement",
    ],
    "physics": [
        "physics", "relativity", "spacetime", "field equation",
        "lagrangian", "hamiltonian",
    ],
    "machine learning": [
        "neural network", "transformer", "attention", "backpropagation",
        "gradient descent", "reinforcement learning", "deep learning",
    ],
    "algorithms": [
        "algorithm", "dynamic programming", "graph algorithm",
        "time complexity", "np-hard",
    ],
    "theory of computation": [
        "turing machine", "computability", "automaton", "regular language",
        "decidability", "complexity class",
    ],
}


# Compact reason-note constants.
NOTE_BOX_W_DOMAIN_BOOST_APPLIED         = "box_w_domain_boost_applied"
NOTE_BOX_W_DOMAIN_BOOST_SKIPPED         = "box_w_domain_boost_skipped"
NOTE_BOX_W_DOMAIN_BOOST_NO_MATCHING     = "box_w_domain_boost_no_matching_result"


@dataclass
class RerankOutcome:
    """Compact inspectable rerank report. Sources/synthesis are the
    reordered outputs; notes explain what happened."""
    sources:   list
    synthesis: str
    notes:     List[str] = field(default_factory=list)
    # Sorted (index → boost_applied) for the returned ordering.
    boosts_applied: List[Tuple[int, float]] = field(default_factory=list)


def _domain_keywords_for(domain: str) -> List[str]:
    """Lowercase keyword list for a given domain string."""
    return [k.lower() for k in _DOMAIN_KEYWORDS.get(domain, [])]


def _match_count(text: str, keywords: List[str]) -> int:
    """Number of domain keyword substring hits in `text`."""
    if not text or not keywords:
        return 0
    t = text.lower()
    return sum(1 for k in keywords if k and k in t)


def rerank_with_domain_anchor(
    sources: list,
    synthesis: str,
    domain_hint: Optional[str],
    *,
    score_attr: str = "relevance_score",
) -> RerankOutcome:
    """Phase G.12 — bounded domain-aware rerank of Box W results.

    Args:
      sources: list of Source-like objects (each has `label`, `uri`,
               `relevance_score`, etc.)
      synthesis: newline-joined text body that parallels `sources` in
               order; reordered along with the sources list
      domain_hint: domain string from `canonical_term_domain_hint`
               (e.g. "category theory"); empty → no-op

    Returns:
      RerankOutcome with reordered sources, rebuilt synthesis, and a
      notes list. When domain_hint is empty OR there is no matching
      source, returns the inputs unchanged with a skipped note.

    This function does NOT mutate the input sources. It constructs
    lightweight `(boosted_score, original_index)` keys, sorts, and
    returns the rearranged views.
    """
    notes: List[str] = []
    if not domain_hint:
        notes.append(NOTE_BOX_W_DOMAIN_BOOST_SKIPPED)
        return RerankOutcome(
            sources=list(sources), synthesis=synthesis, notes=notes,
        )
    keywords = _domain_keywords_for(domain_hint)
    if not keywords or not sources:
        notes.append(NOTE_BOX_W_DOMAIN_BOOST_SKIPPED)
        return RerankOutcome(
            sources=list(sources), synthesis=synthesis, notes=notes,
        )

    # Synthesis is newline-joined; split in parallel.
    synth_parts = (synthesis or "").split("\n\n") if synthesis else []

    scored: List[Tuple[float, int, float]] = []   # (combined, orig_idx, boost)
    any_boosted = False
    for i, src in enumerate(sources):
        raw = float(getattr(src, score_attr, 0.0) or 0.0)
        title_text = (getattr(src, "label", "") or "") + " " + (getattr(src, "uri", "") or "")
        body_text = synth_parts[i] if i < len(synth_parts) else ""
        title_hits = _match_count(title_text, keywords)
        body_hits  = _match_count(body_text, keywords)
        boost = 0.0
        if title_hits > 0:
            boost += DOMAIN_BOOST_TITLE_HIT
        if body_hits > 0:
            boost += DOMAIN_BOOST_BODY_HIT
        boost = min(boost, DOMAIN_BOOST_MAX_TOTAL)
        if boost > 0:
            any_boosted = True
        scored.append((raw + boost, i, boost))

    # Stable sort: highest combined first; preserve original order on ties.
    scored.sort(key=lambda t: (-t[0], t[1]))

    new_sources: list = []
    new_synth_parts: List[str] = []
    boosts: List[Tuple[int, float]] = []
    for rank, (_combined, orig_idx, boost) in enumerate(scored):
        new_sources.append(sources[orig_idx])
        if orig_idx < len(synth_parts):
            new_synth_parts.append(synth_parts[orig_idx])
        if boost > 0:
            boosts.append((orig_idx, round(boost, 4)))

    if any_boosted:
        notes.append(NOTE_BOX_W_DOMAIN_BOOST_APPLIED)
        notes.append(f"box_w_domain_boost_domain={domain_hint}")
    else:
        notes.append(NOTE_BOX_W_DOMAIN_BOOST_NO_MATCHING)

    return RerankOutcome(
        sources=new_sources,
        synthesis="\n\n".join(new_synth_parts) if new_synth_parts else synthesis,
        notes=notes,
        boosts_applied=boosts,
    )
