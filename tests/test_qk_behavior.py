"""
QK behavior verification tests
5 test cases — Sprint 1 completion criteria

These tests verify ISM+QK integration at the appraisal level.
They do NOT require the FAISS index — they test the pattern-based
detection that is already in appraisal.py.

Author : Taiko Toeda / MOBIUS LLC
"""
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.kernel.appraisal import Appraiser
from src.kernel.route_decision import select_route


QK_TEST_CASES = [
    {
        "id": "QK-T01",
        "query": "明日の株価は？",
        "metadata": None,
        "expected_route": "verify",
        "description": "Future prediction — must route to verify (freshness: 明日)",
    },
    {
        "id": "QK-T02",
        "query": "水の沸点は？",
        "metadata": None,
        "expected_route": "answer",
        "description": "Stable fact — answerable directly",
    },
    {
        "id": "QK-T03",
        "query": "現在の日本の首相は？",
        "metadata": None,
        "expected_route": "verify",
        "description": "Current officeholder — must verify",
    },
    {
        "id": "QK-T04",
        "query": "What is the speed of light?",
        "metadata": None,
        "expected_route": "answer",
        "description": "Stable physical constant — answerable",
    },
    {
        "id": "QK-T05",
        "query": "り",
        "metadata": {"prev_assistant": "しりとりをしましょう。象"},
        "expected_route": "answer",
        "description": "Game context — answer directly, no wiki lookup",
    },
]


class TestQKBehavior:
    """QK behavior verification — Sprint 1 completion criteria."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.appraiser = Appraiser()

    @pytest.mark.parametrize("case", QK_TEST_CASES, ids=[c["id"] for c in QK_TEST_CASES])
    def test_qk_routing(self, case):
        appraisal = self.appraiser.evaluate(
            case["query"],
            metadata=case.get("metadata"),
        )
        decision = select_route(appraisal)
        assert decision.route == case["expected_route"], (
            f"{case['id']}: expected route={case['expected_route']}, "
            f"got route={decision.route}. "
            f"Description: {case['description']}. "
            f"Notes: {appraisal.notes}"
        )
