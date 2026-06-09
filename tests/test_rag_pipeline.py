import pytest
from src.retrieval.chunker import chunk_text
from src.retrieval.vector_index import IndexedChunk, InMemoryVectorIndex
from src.retrieval.retrieval_selector import choose_retrieval_plan


# ── chunker ──────────────────────────────────────────────────────────────────

def test_chunk_text_basic():
    text   = "a" * 2000
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)


def test_chunk_text_overlap():
    text   = "abcdefghij" * 100
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    # Second chunk should overlap with first
    assert chunks[1][:50] == chunks[0][150:200]


def test_chunk_text_invalid():
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=100, overlap=100)


# ── vector_index ─────────────────────────────────────────────────────────────

def test_vector_index_search():
    index = InMemoryVectorIndex()
    index.add(IndexedChunk(text="hello world", source="doc1.md", embedding=[1.0, 0.0]))
    index.add(IndexedChunk(text="goodbye",     source="doc2.md", embedding=[0.0, 1.0]))
    results = index.search(query_embedding=[1.0, 0.0], top_k=1)
    assert results[0].text == "hello world"


# ── retrieval_selector (already tested, spot-check here) ─────────────────────

def test_retrieval_selector_local_first():
    plan = choose_retrieval_plan(freshness_sensitive=True, local_hits_available=True)
    assert plan.use_local_rag is True
    assert plan.use_web_search is False
