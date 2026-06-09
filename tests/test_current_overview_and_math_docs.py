from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_current_system_overview_is_rc3_3_aware():
    text = (ROOT / "docs/current/MMV_SYSTEM_OVERVIEW_RC3_3.md").read_text(
        encoding="utf-8"
    )
    for phrase in [
        "MMV-S-RC3.3",
        "MMV-L-RC3.3",
        "MMV-M-RC3.3",
        "L0 v8.4",
        "date_bound_answer",
        "re_anchor",
    ]:
        assert phrase in text


def test_current_math_doctrine_is_rc3_3_aware():
    text = (
        ROOT / "docs/current/MMV_MATHEMATICAL_MODELING_DOCTRINE_RC3_3.md"
    ).read_text(encoding="utf-8")
    for phrase in [
        "R = {answer, ask, verify, date_bound_answer, re_anchor, abstain}",
        "explore` is not a Core route",
        "Small  = 9B RoutingEngine",
        "Large  = RC3.2 doctrine path",
        "Medium = Large stack shape",
        "claim_scope <= evidence_scope",
    ]:
        assert phrase in text


def test_current_sources_are_ingested_into_boxes():
    box0 = json.loads(
        (ROOT / "data/box_0/index_manifest.json").read_text(encoding="utf-8")
    )
    boxa = json.loads(
        (ROOT / "data/box_a/index_manifest.json").read_text(encoding="utf-8")
    )
    assert "MMV_SYSTEM_OVERVIEW_RC3_3.md" in box0.get("files", {})
    assert "MMV_SYSTEM_OVERVIEW_RC3_3.md" in boxa.get("files", {})
    assert (
        "MMV_Mathematical_Modeling_Doctrine_and_Formalism_EN.md"
        in boxa.get("files", {})
    )
    assert boxa.get("model") == "intfloat/multilingual-e5-large"


def test_box_a_index_is_me5_dimensional():
    faiss = pytest.importorskip("faiss")
    idx = faiss.read_index(str(ROOT / "data/box_a/custom_index.faiss"))
    assert idx.d == 1024
