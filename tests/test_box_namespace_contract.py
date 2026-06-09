from pathlib import Path

from src.adapters.retrieval_selector import BoxFlags, RetrievalSelector


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_box_namespace_declares_current_roles() -> None:
    text = _read("docs/BOX_NAMESPACE.md")

    assert "**Box B** | 🅴 **Reserved document slot**" in text
    assert "**Box C** | 🅴 **Reserved document slot**" in text
    assert "**Box W** | Wikipedia" in text
    assert "**Box S** | **External / web search (Brave)**" in text

    assert "| **Box C** | External search" not in text
    assert "**Box B** = **personal context**" not in text


def test_current_operator_surfaces_do_not_use_legacy_box_labels() -> None:
    current_surfaces = {
        "README.md": _read("README.md"),
        "CLAUDE.md": _read("CLAUDE.md"),
        "docs/EMBEDDING_RULE.md": _read("docs/EMBEDDING_RULE.md"),
        "docs/HF_WIKI_DATASET_README_TEMPLATE.md": _read(
            "docs/HF_WIKI_DATASET_README_TEMPLATE.md"
        ),
        "docs/PUBLIC_RELEASE_PROCEDURE.md": _read("docs/PUBLIC_RELEASE_PROCEDURE.md"),
        "THIRD_PARTY_LICENSES.md": _read("THIRD_PARTY_LICENSES.md"),
        "config/wiki_index_source.yaml": _read("config/wiki_index_source.yaml"),
        "scripts/fetch_wiki_index.py": _read("scripts/fetch_wiki_index.py"),
        "src/ui/app.py": _read("src/ui/app.py"),
        "src/adapters/retrieval_selector.py": _read("src/adapters/retrieval_selector.py"),
    }

    forbidden = (
        "Wiki (Box B)",
        "Wikipedia / Box B",
        "Box B (Wikipedia)",
        "Box C (Brave",
        "Box C freshness",
        "[BoxC]",
        "Box B runtime",
        "shares Box B",
    )
    for path, text in current_surfaces.items():
        for needle in forbidden:
            assert needle not in text, f"{path} still contains {needle!r}"


def test_box_w_env_flag_and_legacy_box_b_alias(monkeypatch) -> None:
    monkeypatch.delenv("MOBIUS_BOX_W", raising=False)
    monkeypatch.delenv("MOBIUS_BOX_B", raising=False)
    assert BoxFlags.from_env().box_b is True

    monkeypatch.setenv("MOBIUS_BOX_B", "0")
    assert BoxFlags.from_env().box_b is False

    monkeypatch.setenv("MOBIUS_BOX_W", "1")
    assert BoxFlags.from_env().box_b is True

    monkeypatch.setenv("MOBIUS_BOX_W", "0")
    assert BoxFlags.from_env().box_b is False


def test_retrieval_selector_repr_uses_w_and_s_labels() -> None:
    selector = RetrievalSelector(box_a=None, box_b=None)
    rendered = repr(selector)

    assert "W=" in rendered
    assert "S=" in rendered
    assert "C=" not in rendered
