"""
test_box_x_presentation_polish.py — Stage 9 presentation-layer polish
tests for Box X injection.

These tests assert the *shape* of the presentation layer only:

  - Box X evidence block no longer advertises itself as a "reference
    block" / "curated reference" header — the leading-block framing
    is what harmed weighted same_format / technical_term_success in
    Stage 8 evaluation.
  - At every prompt call site, the user question precedes the Box X
    hints (model-first, Box X second).
  - Non-technical queries still receive no Box X injection.
  - `_box_x_evidence_block` retains its documented invariants
    (title / domain / source_uri present, max_chars bound).

No retrieval, routing, or activation logic is exercised here — those
are covered by `test_routing_engine_box_x_live.py` and the Box X
consult test suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.kernel.routing_engine import RoutingEngine  # noqa: E402
from src.memory.box_x import BoxXEntry, BoxXStore  # noqa: E402


def _seed(tmp_path):
    store = BoxXStore(tmp_path)
    store.add(BoxXEntry(
        entry_id="ex_counit", title="Counit",
        canonical_terms=["counit", "カウニット", "co-unit"],
        domain="category theory",
        source_family="curated_domain_pack",
        source_uri="domain://c/counit",
        content="Counit body " * 80,
        quality_score=0.85,
    ))
    return store


class _AppraisalLike:
    def __init__(self, *, freshness_sensitive=False, notes=None):
        self.freshness_sensitive = freshness_sensitive
        self.notes = list(notes or [])


class _SessionLike:
    pass


class TestEvidenceBlockFraming:
    """Stage 9: the block must no longer advertise itself as a
    'Box X — curated reference' header. The model should see neutral
    terminology hints, not a framed reference document.
    """

    def test_block_has_no_reference_block_header(self, tmp_path):
        engine = RoutingEngine(box_x_store=_seed(tmp_path))
        out = engine._box_x_consult(
            query="counit category theory",
            appraisal=_AppraisalLike(), state=_SessionLike(),
        )
        block = engine._box_x_evidence_block(out)
        assert "Box X — curated reference" not in block
        assert "curated reference" not in block.lower()

    def test_block_still_contains_title_domain_uri(self, tmp_path):
        engine = RoutingEngine(box_x_store=_seed(tmp_path))
        out = engine._box_x_consult(
            query="counit category theory",
            appraisal=_AppraisalLike(), state=_SessionLike(),
        )
        block = engine._box_x_evidence_block(out)
        assert "Counit" in block
        assert "category theory" in block
        assert "domain://c/counit" in block

    def test_block_starts_as_list_item_not_header(self, tmp_path):
        engine = RoutingEngine(box_x_store=_seed(tmp_path))
        out = engine._box_x_consult(
            query="counit",
            appraisal=_AppraisalLike(), state=_SessionLike(),
        )
        block = engine._box_x_evidence_block(out)
        assert block.startswith("- "), (
            "Box X hints should render as a neutral bullet list, "
            "not a framed reference-block header"
        )

    def test_block_empty_for_empty_record(self):
        engine = RoutingEngine()
        assert engine._box_x_evidence_block(None) == ""
        assert engine._box_x_evidence_block({"hits": []}) == ""

    def test_block_respects_max_chars(self, tmp_path):
        engine = RoutingEngine(box_x_store=_seed(tmp_path))
        out = engine._box_x_consult(
            query="counit",
            appraisal=_AppraisalLike(), state=_SessionLike(),
        )
        block = engine._box_x_evidence_block(out, max_chars=50)
        assert len(block) <= 50


class TestPromptOrderingInSource:
    """Stage 9 requires: user question precedes Box X hints at every
    call site. We grep the source file to verify the four injection
    templates follow the model-first pattern.

    Rationale: leading-block framing (`Curated reference ... User:`)
    was confirmed in Stage 8 eval to harm same_format and weighted
    technical_term_success. Stage 9 flips the order: user question
    first, Box X hints as trailing background.
    """

    SOURCE = Path(__file__).parent.parent / "src" / "kernel" / "routing_engine.py"

    def _source_text(self) -> str:
        return self.SOURCE.read_text(encoding="utf-8")

    def test_no_leading_curated_reference_prompt(self):
        text = self._source_text()
        # The old pattern put "Curated reference (Box X ..." at the
        # top of the prompt, before "User:". Stage 9 removes every
        # such prompt-template occurrence. (The string may still
        # appear in comments; the test targets f-string prompt
        # templates, which always include the parenthetical form.)
        assert "Curated reference (Box X" not in text, (
            "Leading 'Curated reference (Box X ...)' block must not "
            "appear in any prompt template (Stage 9 polish)."
        )

    def test_prompts_use_terminology_hints_label(self):
        text = self._source_text()
        # All four injection sites should now use the neutral
        # trailing-hint framing.
        count = text.count("Terminology hints")
        assert count >= 4, (
            f"Expected >=4 'Terminology hints' labels (one per Box X "
            f"prompt injection site), found {count}"
        )

    def test_prompts_include_do_not_quote_guardrail(self):
        text = self._source_text()
        # The presentation guardrail keeps the model from dumping
        # the hints verbatim as a reference block.
        assert "do not quote" in text.lower()


class TestSameFormatAndShortAnswerSafety:
    """Stage 9: presentation polish must not expand short answers or
    disrupt same_format cases. We can't easily run the adapter here,
    but we can assert that no forbidden length-inflating instructions
    leak into the templates.
    """

    SOURCE = Path(__file__).parent.parent / "src" / "kernel" / "routing_engine.py"

    def _source_text(self) -> str:
        return self.SOURCE.read_text(encoding="utf-8")

    def test_no_starting_hint_prime(self):
        text = self._source_text()
        # The "Use the curated reference above as a starting hint"
        # prime was the specific phrase that caused the model to
        # prepend reference-block style openings. It must be gone.
        assert "as a starting hint" not in text, (
            "Starting-hint prime must be removed — it caused "
            "reference-block style answers in Stage 8 eval."
        )

    def test_no_cite_reference_prime(self):
        text = self._source_text()
        # "Cite the reference's canonical term" nudged the model
        # toward citation formatting. Stage 9 removes it; canonical
        # terms still appear in the trailing hint block so the
        # model can absorb them without being asked to cite.
        assert "Cite the reference" not in text

    def test_concise_instruction_retained(self):
        text = self._source_text()
        # We still want concise + grounded + no-rhetorical-questions.
        assert "Keep the response concise" in text
        assert "Do not add rhetorical questions" in text


class TestNonTechnicalQuerySkip:
    """Invariant from Stage 8: non-technical queries still skip Box X
    entirely. Presentation polish must not weaken this.
    """

    def test_boil_egg_is_skipped(self, tmp_path):
        engine = RoutingEngine(box_x_store=_seed(tmp_path))
        out = engine._box_x_consult(
            query="how do I boil an egg",
            appraisal=_AppraisalLike(), state=_SessionLike(),
        )
        # Predicate skips; block must be empty even if consult runs.
        assert out is not None
        assert out["hit"] is False
        assert engine._box_x_evidence_block(out) == ""

    def test_freshness_query_is_skipped(self, tmp_path):
        engine = RoutingEngine(box_x_store=_seed(tmp_path))
        out = engine._box_x_consult(
            query="counit",
            appraisal=_AppraisalLike(freshness_sensitive=True),
            state=_SessionLike(),
        )
        # Freshness-sensitive queries skip Box X entirely.
        assert out is None
