from __future__ import annotations

from typing import Any, Dict, List, Optional


def determine_knowledge_source(response_text: str, sources: list, route: str) -> str:
    """Classify the knowledge source used for the response.

    Returns: "retrieved", "model", "mixed", or "none".
    """
    if route == "abstain":
        return "none"

    model_markers = [
        "モデルの知識に基づいて", "model knowledge",
        "検索ソースに直接的な情報が見つからなかった",
        "No directly relevant sources",
        "外部ソースによる検証はできていません",
        "external verification was not available",
        "未找到直接相关来源",
    ]
    has_sources = bool(sources)
    has_model_fallback = any(m in response_text for m in model_markers)

    if has_sources and has_model_fallback:
        return "mixed"
    elif has_sources:
        return "retrieved"
    elif has_model_fallback:
        return "model"
    else:
        return "retrieved" if route == "answer" else "none"


def build_trace(
    route:           str,
    reason_codes:    List[str],
    verify_outcome:  Optional[str],
    sources:         List[str],
    active_language: str,
    explanation:     str,
    eal_detail:      Optional[Dict[str, Any]] = None,
    phi_t:           Optional[float] = None,
    rgc_band:        Optional[str]   = None,
    rgc_pi:          Optional[float] = None,
    box_a_detail:    Optional[Dict[str, Any]] = None,
    box_x_detail:    Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a structured trace record.

    Control-layer fields are always English.
    explanation is in active_language.
    eal_detail is populated when the EAL verify path was executed.
    """
    ks = determine_knowledge_source(explanation, sources, route)
    trace: Dict[str, Any] = {
        "Route":            route,
        "Reason":           ", ".join(reason_codes),
        "VerifyOutcome":    verify_outcome,
        "Sources":          sources,
        "KnowledgeSource":  ks,
        "ActiveLanguage":   active_language,
        "Explanation":      explanation,
        "RGC_phi_t":        round(phi_t, 4) if phi_t is not None else None,
        "RGC_band":         rgc_band,
        "RGC_pi":           round(rgc_pi, 4) if rgc_pi is not None else None,
    }

    if eal_detail:
        trace.update({
            "UsedLocalEvidence":              eal_detail.get("UsedLocalEvidence"),
            "UsedWebSearch":                  eal_detail.get("UsedWebSearch"),
            "WhyWebSearchWasTriggered":        eal_detail.get("WhyWebSearchWasTriggered"),
            "WhyLocalEvidenceWasInsufficient": eal_detail.get("WhyLocalEvidenceWasInsufficient"),
            "SearchProvider":                 eal_detail.get("SearchProvider"),
            "Admissibility":                  eal_detail.get("Admissibility"),
            "ConflictState":                  eal_detail.get("ConflictState"),
            "FreshnessState":                 eal_detail.get("FreshnessState"),
        })

    if box_a_detail:
        trace["BoxA_mode"] = box_a_detail.get("mode")
        trace["BoxA_filenames"] = box_a_detail.get("filenames", [])
        trace["BoxA_top_score"] = box_a_detail.get("top_score")
        trace["BoxA_compliant"] = box_a_detail.get("compliant")

    # Stage 6 — Box X (curated external durable knowledge) trace fields.
    if box_x_detail:
        trace["BoxX_consulted"] = bool(box_x_detail.get("consulted"))
        trace["BoxX_hit"]       = bool(box_x_detail.get("hit"))
        trace["BoxX_reason"]    = box_x_detail.get("reason")
        trace["BoxX_hit_count"] = len(box_x_detail.get("hits") or [])
        trace["BoxX_titles"]    = [
            h.get("title", "") for h in (box_x_detail.get("hits") or [])
        ][:5]

    return trace
