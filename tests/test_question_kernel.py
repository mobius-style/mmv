"""
test_question_kernel.py — Question Kernel selection and formatting tests.

Author : Taiko Toeda / MOBIUS LLC
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.adapters.question_kernel import (
    select_kernels,
    format_kernel_block,
    get_zone_for_intent,
)


class TestSelectKernels:

    def test_abstain_returns_empty(self):
        kernels = select_kernels("factual_query", route="abstain")
        assert kernels == []

    def test_ask_returns_empty(self):
        kernels = select_kernels("factual_query", route="ask")
        assert kernels == []

    def test_light_zone_always_fire_only(self):
        kernels = select_kernels("casual_greeting", zone="light")
        ids = [k["id"] for k in kernels]
        assert "QK_08" not in ids  # pro-only zone override
        for k in kernels:
            assert "light" in k["applies_to_zones"]

    def test_standard_zone(self):
        kernels = select_kernels("factual_query", zone="standard")
        ids = [k["id"] for k in kernels]
        assert "QK_01" in ids  # always_fire, all zones
        assert "QK_08" not in ids  # pro-only

    def test_pro_zone_includes_context_dependent(self):
        kernels = select_kernels("correction", zone="pro")
        ids = [k["id"] for k in kernels]
        assert "QK_08" in ids  # pro-only always_fire
        context_dep = {"QK_29", "QK_15", "QK_23", "QK_34",
                       "QK_09", "QK_22", "QK_32"}
        assert len(context_dep & set(ids)) > 0

    def test_suppressed_not_selected(self):
        """Phase 2: QK_07/19/10/20 remain suppressed."""
        suppressed = {"QK_07", "QK_19", "QK_10", "QK_20"}
        for intent in ["factual_query", "correction", "meta_question"]:
            kernels = select_kernels(intent, zone="pro")
            ids = set(k["id"] for k in kernels)
            assert len(suppressed & ids) == 0, \
                f"Suppressed QK found for {intent}: {suppressed & ids}"


class TestFormatKernelBlock:

    def test_format_kernel_block_empty(self):
        assert format_kernel_block([]) == ""

    def test_format_kernel_block_numbered(self):
        kernels = select_kernels("factual_query", zone="standard")
        block = format_kernel_block(kernels)
        assert "[INTERNAL METACOGNITIVE CHECK" in block
        assert "1." in block


class TestGetZone:

    def test_get_zone_for_intent(self):
        assert get_zone_for_intent("casual_greeting") == "light"
        assert get_zone_for_intent("factual_query") == "standard"
        assert get_zone_for_intent("correction") == "pro"
        assert get_zone_for_intent("unknown_type") == "standard"


class TestISMIntegration:

    def test_translation_override_standard(self):
        kernels = select_kernels("translation_request", "standard", "answer")
        ids = sorted(k["id"] for k in kernels)
        assert ids == ["QK_03", "QK_13", "QK_14", "QK_24", "QK_31"]

    def test_translation_override_pro(self):
        kernels = select_kernels("translation_request", "pro", "answer")
        ids = sorted(k["id"] for k in kernels)
        assert ids == ["QK_03", "QK_13", "QK_14", "QK_24", "QK_31"]

    def test_casual_greeting_suppressed(self):
        kernels = select_kernels("casual_greeting", "standard", "answer")
        ids = set(k["id"] for k in kernels)
        excluded = {"QK_08", "QK_15", "QK_21", "QK_23", "QK_32", "QK_34"}
        assert len(excluded & ids) == 0, f"Should be excluded: {excluded & ids}"

    def test_factual_query_pro_includes_qk09(self):
        kernels = select_kernels("factual_query", "pro", "answer")
        ids = [k["id"] for k in kernels]
        assert "QK_09" in ids

    def test_instruction_request_pro_excludes_qk09(self):
        kernels = select_kernels("instruction_request", "pro", "answer")
        ids = [k["id"] for k in kernels]
        assert "QK_09" not in ids

    def test_abstain_returns_empty(self):
        kernels = select_kernels("creative_request", "standard", "abstain")
        assert kernels == []
