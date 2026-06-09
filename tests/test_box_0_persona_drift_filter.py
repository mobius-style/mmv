"""Box 0 persona-drift post-filter — contract tests.

Per Evolution Log cyc_20260423_production_failure_deep_fix_2 (Layer 8):
v8.2 L0 protocol includes embedded JSON add-on examples (medical_support
"clinical note helper", K-12 learner feedback, chronic disease
adherence, etc.) which, after ME5 encoding for Box 0, rank very close
to canonical identity chunks on self-reference queries. For
「貴方の特徴を教えてください」 the pre-fix top-3 contained one
medical-persona example at score 0.8005.

The fix: retrieve top_k*2 from Box 0, then demote chunks that match
persona/add-on markers by a factor of 0.5, and take the top_k after
re-sort. Demotion — not exclusion — so a legitimately relevant add-on
chunk can still surface when no canonical chunk outranks it.

These tests are marker-only (no ME5 model load) plus one integration
test with the real Box 0 index:

  1. `_looks_like_persona_addon_chunk` flags the known v8.2 markers.
  2. `_looks_like_persona_addon_chunk` ignores canonical identity text.
  3. Real Box 0 retrieve: 「貴方の特徴」 top-3 contains no persona chunks.
  4. Real Box 0 retrieve: 「自己紹介してください」 top-3 contains no
     persona chunks.
  5. Real Box 0 retrieve: the demotion factor constant is 0.5 as
     documented in docs/ and the Evolution Log.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.kernel.routing_engine import (
    _looks_like_persona_addon_chunk,
    _PERSONA_DEMOTION_FACTOR,
    _PERSONA_MARKER_SUBSTRINGS,
)

ROOT = Path(__file__).resolve().parents[1]
BOX_0_DIR = ROOT / "data" / "box_0"


# ── Group 1: Marker detection (pure helper) ────────────────────────────────

PERSONA_POSITIVE_SAMPLES = [
    '{ "trigger_phrases": [ "clinical note helper" ] }',
    '{"Q3_longterm": [{"notes": "Encourage adherence to chronic disease management"}]}',
    "diagnose and prescribe medications for patients",
    "K-12 learner feedback is important",
    "If the learner repeated a bit hard, or very hard to follow",
    '"Q_meta_frame": [ "unhelpful meta-frames" ]',
]

PERSONA_NEGATIVE_SAMPLES = [
    # Canonical identity content
    '"appraisal", "qk", "ism", "half-step", "answer entitlement", "メビウス"',
    "# PART VI: THE RUNTIME ARCHITECTURE ## Answer Entitlement and L0",
    "MOBIUS MMV is a reflective conversation runtime",
    "Box 0 is the self-reference layer of the 9-box namespace",
    # Empty / whitespace
    "",
    "   ",
]


@pytest.mark.parametrize("text", PERSONA_POSITIVE_SAMPLES)
def test_marker_detection_positive(text: str) -> None:
    assert _looks_like_persona_addon_chunk(text), (
        f"Persona-addon marker text should flag positive: {text[:60]!r}"
    )


@pytest.mark.parametrize("text", PERSONA_NEGATIVE_SAMPLES)
def test_marker_detection_negative(text: str) -> None:
    assert not _looks_like_persona_addon_chunk(text), (
        f"Canonical identity text must not flag as persona addon: "
        f"{text[:60]!r}"
    )


# ── Group 2: Demotion factor constant ─────────────────────────────────────

def test_demotion_factor_is_half() -> None:
    # Locked-in value — changing this is a scope decision recorded in
    # Evolution Log / EMBEDDING_RULE. Demotion (not exclusion) preserves
    # the fallback behavior where an add-on chunk can still surface if
    # no canonical chunk outranks it.
    assert _PERSONA_DEMOTION_FACTOR == 0.5


def test_persona_marker_list_nonempty() -> None:
    # At minimum the v8.2 clinical / K-12 markers must remain. Adding
    # markers is always safe; removing them is a regression.
    assert len(_PERSONA_MARKER_SUBSTRINGS) >= 5
    assert '"trigger_phrases"' in _PERSONA_MARKER_SUBSTRINGS
    assert "clinical note helper" in _PERSONA_MARKER_SUBSTRINGS
    assert "K-12 learner" in _PERSONA_MARKER_SUBSTRINGS


# ── Group 3: Integration — real Box 0 retrieve via RoutingEngine helper ────

@pytest.fixture(scope="module")
def routing_engine_with_box_0():
    """Spin up a RoutingEngine with only Box 0 wired — enough to exercise
    `_retrieve_box_0_filtered` end-to-end. Skipped when the Box 0 index
    is not present (fresh checkout with no rebuild yet).
    """
    if not (BOX_0_DIR / "custom_index.faiss").exists():
        pytest.skip("Box 0 index not present")

    from src.adapters.custom_rag_adapter import CustomRagAdapter
    from src.kernel.routing_engine import RoutingEngine

    adapter = CustomRagAdapter(
        corpus_dir     = str(ROOT / "corpus_box_0"),
        data_dir       = str(BOX_0_DIR),
        watch          = False,
        model_name     = "intfloat/multilingual-e5-large",
        query_prefix   = "query: ",
        passage_prefix = "passage: ",
    )
    adapter.load()

    engine = RoutingEngine(
        adapter=None,
        web_search_adapter=None,
        kiwix_adapter=None,
        box_0_adapter=adapter,
        wiki_adapter=None,
    )
    return engine


def _top_k_has_persona(result) -> bool:
    """True if any text in the synthesis looks like a persona add-on."""
    if not result or not result.synthesis:
        return False
    for chunk_text in result.synthesis.split("\n\n"):
        if _looks_like_persona_addon_chunk(chunk_text):
            return True
    return False


@pytest.mark.parametrize("query", [
    "貴方の特徴を教えてください",
    "自己紹介してください",
    "あなたは誰ですか",
    "MOBIUS とは何ですか",
])
def test_filtered_retrieve_excludes_persona_from_top_k(
    routing_engine_with_box_0, query: str,
) -> None:
    # Integration: retrieve top_k=3 via the filter and confirm no persona
    # add-on chunks slipped through. Demotion factor 0.5 is enough to
    # push c#106 / c#107 (the v8.2 medical example chunks at ~0.80 raw
    # score) out of the top-3 on these queries.
    r = routing_engine_with_box_0._retrieve_box_0_filtered(query, top_k=3)
    assert r is not None
    assert r.sources, f"Box 0 should return some sources for {query!r}"
    assert not _top_k_has_persona(r), (
        f"Box 0 filtered retrieve for {query!r} still contains a "
        f"persona-addon chunk in top-3. synthesis head: "
        f"{(r.synthesis or '')[:200]!r}"
    )


def test_filtered_retrieve_preserves_ordering_on_no_markers(
    routing_engine_with_box_0,
) -> None:
    # For a query that does not surface any persona chunks in the wider
    # pool, the filter should preserve the native FAISS ordering.
    query = "Answer Entitlement とは"
    r_raw = routing_engine_with_box_0.box_0_adapter.retrieve(query, top_k=3)
    r_filt = routing_engine_with_box_0._retrieve_box_0_filtered(query, top_k=3)
    assert r_filt is not None
    assert r_raw.sources and r_filt.sources
    # Top-1 should be the same when neither result was demoted.
    assert r_raw.sources[0].label == r_filt.sources[0].label
    assert r_raw.sources[0].chunk_index == r_filt.sources[0].chunk_index


def test_filtered_retrieve_returns_none_when_no_adapter() -> None:
    # Defensive: when no Box 0 adapter is wired, the helper must return
    # None rather than raising, so the caller's `if _r is not None`
    # guard behaves identically to the legacy try/except.
    from src.kernel.routing_engine import RoutingEngine
    engine = RoutingEngine(
        adapter=None, web_search_adapter=None, kiwix_adapter=None,
        box_0_adapter=None, wiki_adapter=None,
    )
    assert engine._retrieve_box_0_filtered("anything", top_k=3) is None
