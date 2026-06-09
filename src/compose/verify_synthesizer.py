"""
verify_synthesizer.py — Source-aware bounded synthesis for the verify route.

Maps AdjudicatedEvidenceSet -> verify outcome + user-facing response text.
Uses the configured model via InferenceAdapter (same model as answer route).
Falls back to a structured text response when no adapter is available.
"""
from __future__ import annotations

from ..adjudication.evidence_models import (
    AdjudicatedEvidenceSet,
    ADMISSIBILITY_ANSWERABLE,
    ADMISSIBILITY_BOUNDED_ONLY,
    ADMISSIBILITY_FAILED,
)

# Verify outcome labels exposed to trace and UI
VERIFY_SUCCESS = "verify_success"
VERIFY_PARTIAL = "verify_partial"
VERIFY_FAILED  = "verify_failed"

# Re-anchor guidance — applied only when verify fails.
# Distinct from HalfStep: re-anchor returns the interaction to firmer ground
# when the system cannot commit, providing one concrete next step.
RE_ANCHOR_GUIDANCE = (
    "\n\nRe-anchor instruction (applies because verify failed):\n"
    "The system could not verify this query. "
    "After stating clearly what could not be confirmed, "
    "provide ONE concrete re-anchor — exactly one of:\n"
    "  (a) a more specific version of the question that would be verifiable,\n"
    "  (b) a specific authoritative source the user can check directly,\n"
    "  (c) a boundary condition that would change the answer status.\n"
    "Rules:\n"
    "  - One re-anchor only. Distance = 1 unit from current state.\n"
    "  - Be specific, not generic.\n"
    "  - Do not apologize excessively.\n"
    "  - Do not explain the system architecture.\n"
    "Wrong: 'I cannot answer. Please provide more context.'\n"
    "Right: 'Current evidence is insufficient to confirm the prime minister. "
    "The official source is kantei.go.jp.'"
)


def _outcome_from_admissibility(admissibility: str) -> str:
    if admissibility == ADMISSIBILITY_ANSWERABLE:
        return VERIFY_SUCCESS
    if admissibility == ADMISSIBILITY_BOUNDED_ONLY:
        return VERIFY_PARTIAL
    return VERIFY_FAILED


def _sources_for_trace(adjudicated: AdjudicatedEvidenceSet) -> list[dict]:
    return [
        {
            "title": item.title,
            "url": item.url,
            "source_name": item.source_name,
            "freshness_state": item.freshness_state,
            "provenance_state": item.provenance_state,
        }
        for item in adjudicated.items
    ]


# RCB_4 (Recency Rule, Outer Conscience backstop per CC_13):
# Freshness priority for programmatic sort. Items whose freshness_state
# indicates more recent / more verified coverage come first, so that LLM
# non-compliance with the recency_rule prompt instruction does not result
# in stale evidence being prioritized. This is the programmatic fallback
# that makes the recency rule an outer conscience (inspectable, adjustable,
# independent of model reasoning) rather than an inner conscience (hidden
# in prompt, opaque to audit).
#
# Values match evidence_models.FRESHNESS_* string literals exactly.
_FRESHNESS_PRIORITY = {
    "current-supported": 0,
    "acceptable":        1,
    "stale-risk":        2,
}


def _sort_items_by_freshness(items):
    """Sort evidence items so that most-recent/most-fresh items appear first.

    Ordering priority (per item):
    1. freshness_state = current-supported (fresh, verified)
    2. freshness_state = acceptable (reasonably current)
    3. freshness_state = stale-risk (last, last resort)
    4. items without freshness_state info: treated as acceptable (middle)

    Within each freshness class, preserve original rank order (stable sort).
    """
    def _key(item):
        state = getattr(item, "freshness_state", None) or "acceptable"
        return _FRESHNESS_PRIORITY.get(state, 1)
    return sorted(items, key=_key)


def _build_evidence_block(adjudicated: AdjudicatedEvidenceSet) -> str:
    """Compact evidence block passed to the model as context.

    RCB_4: items are sorted by freshness_state before enumeration so that
    freshness precedence is enforced programmatically, not only via the
    recency_rule prompt instruction in _build_prompt.
    """
    items = _sort_items_by_freshness(adjudicated.items)
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(
            f"[{i}] {item.source_name} — {item.title}\n"
            f"    {item.snippet}\n"
            f"    URL: {item.url}"
        )
    return "\n\n".join(lines)


def _build_prompt(
    query: str,
    outcome: str,
    evidence_block: str,
    adjudicated: AdjudicatedEvidenceSet,
    active_language: str,
    preset_tone: str = "",
    tvs: float = 0.25,
    mkr: float = 0.55,
    canonical_term_hint: str = "",
) -> str:
    # cyc_20260424_pattern_c_full_synthesis_retrieval_fix:
    # Posture notes rewritten to enforce evidence-fidelity. Previous
    # wording for VERIFY_FAILED / the fallback_rule below explicitly
    # encouraged "use your own knowledge instead" when evidence was
    # irrelevant, which caused confident base-model hallucination on
    # Krillin-class queries (ZH 希拉里·克林顿, EN Bulma). The revised
    # posture is: evidence first; if evidence is silent or contradicts,
    # state uncertainty honestly rather than falling back to training.
    posture_note = {
        VERIFY_SUCCESS: (
            "The evidence set is sufficient for a bounded answer. "
            "Answer directly and cite the sources. "
            "If your internal knowledge disagrees with the sources, "
            "DEFER TO THE SOURCES — do not override evidence with "
            "training knowledge."
        ),
        VERIFY_PARTIAL: (
            "The evidence is partial or conflicting. "
            "Answer ONLY what the sources clearly support. "
            "Explicitly state what remains uncertain. "
            "Do NOT fill gaps with your training knowledge as if it "
            "were fact — if evidence is silent on a sub-question, "
            "say so in one sentence."
        ),
        VERIFY_FAILED: (
            "The retrieved evidence does NOT directly address the "
            "question. DO NOT fabricate a specific answer. "
            "Preferred responses (pick the most honest):\n"
            "  1. State clearly that the retrieved sources do not "
            "contain the answer, and name ONE specific authoritative "
            "source the user could check directly.\n"
            "  2. If you have uncontroversial, widely-agreed "
            "background knowledge (e.g. basic science, universally-"
            "known historical fact), you MAY provide it as context — "
            "but prepend: "
            "'※ No directly relevant sources found — answering from "
            "model knowledge.' "
            "(JP: '※ 検索ソースに直接的な情報が見つからなかったため、"
            "モデルの知識に基づいて回答します。') "
            "(ZH: '※ 未找到直接相关来源，基于模型知识回答。')\n"
            "CRITICAL: for questions about SPECIFIC ENTITIES "
            "(person's spouse / child / role / status / position), do "
            "NOT commit to a specific name or identity from training "
            "alone. State honest uncertainty instead. This rule "
            "applies across Japanese, English, and Chinese."
            + RE_ANCHOR_GUIDANCE
        ),
    }[outcome]

    conflict_note = (
        " Note: sources show conflicting signals — reflect this in your response."
        if adjudicated.conflict_state == "open-conflict"
        else ""
    )

    tone_note = f"\n{preset_tone}" if preset_tone else ""

    kvs_header = (
        "[Evidence governance — internal, do not mention in response]\n"
        f"TVS={tvs:.2f}"
        f" ({'high-volatility: use conditional grammar' if tvs >= 0.6 else 'stable'})\n"
        f"MKR={mkr:.2f}"
        f" ({'unreliable: prefer evidence over model knowledge' if mkr < 0.5 else 'reliable'})\n"
        f"admissibility={outcome}\n\n"
    )

    # cyc_20260424_pattern_c_full_synthesis_retrieval_fix: rewritten
    # to prefer honest-uncertainty over base-model-knowledge
    # fabrication. The previous "Use your own knowledge instead"
    # instruction was the direct driver of Krillin-class hallucinations
    # (Bulma / Hillary Clinton) on irrelevant-evidence cases.
    fallback_rule = (
        "\nIMPORTANT: If the sources above are irrelevant to the "
        "question, do NOT invent a specific answer from training "
        "knowledge. For specific-entity questions (who is X's "
        "spouse, what is Y's role, etc.) say clearly that the "
        "retrieved sources do not cover this, and either name an "
        "authoritative source the user can check, or state honest "
        "uncertainty. Only provide a background answer if the topic "
        "is broad and uncontroversial (basic science, widely-agreed "
        "historical fact) — and only with the explicit prepend "
        "marker shown in the posture instruction."
    )

    recency_rule = (
        "\nWhen the query asks about the current holder of a position, "
        "status, or title, prioritize the most recent temporal evidence "
        "in the sources. Dates, succession markers, and chronological "
        "ordering indicate recency. The most prominently mentioned "
        "entity is not necessarily the current one — a predecessor "
        "may have more coverage than the current holder."
    )

    # Phase G.10 — canonical-term synthesis bridge. Short glossary line
    # surfaced when the upstream query reformulator found a canonical
    # mapping. Helps the model stay anchored on the canonical English
    # term (e.g. "ユニット射 = unit morphism") instead of drifting into
    # similarly-spelled irrelevant concepts.
    canonical_block = (
        f"Canonical glossary (use the canonical English term where "
        f"relevant): {canonical_term_hint}\n\n"
    ) if canonical_term_hint else ""

    return (
        f"{kvs_header}"
        f"{canonical_block}"
        f"Evidence retrieved for verification:\n\n"
        f"{evidence_block}\n\n"
        f"Question: {query}\n\n"
        f"Respond in {active_language}.\n"
        f"{posture_note}{conflict_note}{tone_note}\n"
        f"Keep the response concise. "
        f"If you cite sources, reference them by number (e.g. [1], [2])."
        f"{fallback_rule}"
        f"{recency_rule}"
    )


def _fallback_text(outcome: str, adjudicated: AdjudicatedEvidenceSet) -> str:
    """Structured text when no InferenceAdapter is available."""
    if outcome == VERIFY_SUCCESS:
        sources_summary = "; ".join(
            f"{it.source_name}" for it in adjudicated.items[:3]
        )
        return (
            f"[verify:success] Evidence found. "
            f"Sources: {sources_summary}. "
            f"Model not connected — attach InferenceAdapter for full synthesis."
        )
    if outcome == VERIFY_PARTIAL:
        return (
            f"[verify:partial] Partial evidence found "
            f"(conflict={adjudicated.conflict_state}, "
            f"freshness={adjudicated.freshness_state}). "
            f"Model not connected — full synthesis requires InferenceAdapter."
        )
    return (
        f"[verify:failed] Insufficient evidence for answer commitment "
        f"(admissibility={adjudicated.admissibility}). "
        f"Verification could not be completed."
    )


def synthesize_verify_response(
    query: str,
    adjudicated: AdjudicatedEvidenceSet,
    active_language: str = "en",
    preset: str = "general",
    adapter=None,           # Optional[InferenceAdapter]
    tvs: float = 0.25,
    mkr: float = 0.55,
    canonical_term_hint: str = "",
) -> dict:
    """
    Return a dict with keys:
      verify_outcome  : str
      response_text   : str
      sources         : list[dict]
      explanation     : str
    """
    outcome = _outcome_from_admissibility(adjudicated.admissibility)
    sources = _sources_for_trace(adjudicated)
    explanation = " | ".join(adjudicated.rationale)

    if adapter and adjudicated.items:
        from ..adjudication.verify_presets import get_preset
        preset_obj   = get_preset(preset)
        evidence_block = _build_evidence_block(adjudicated)
        prompt = _build_prompt(
            query, outcome, evidence_block, adjudicated, active_language,
            preset_tone=preset_obj.tone_note, tvs=tvs, mkr=mkr,
            canonical_term_hint=canonical_term_hint,
        )

        from ..adapters.inference_adapter import KernelRequest
        req  = KernelRequest(user_input=query, prompt=prompt)
        resp = adapter.generate(req)
        response_text = resp.text
    else:
        response_text = _fallback_text(outcome, adjudicated)

    return {
        "verify_outcome": outcome,
        "response_text":  response_text,
        "sources":        sources,
        "explanation":    explanation,
    }
