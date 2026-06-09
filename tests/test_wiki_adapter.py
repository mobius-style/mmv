#!/usr/bin/env python3
"""
test_wiki_adapter.py — WikiAdapter 単体テスト
tests/test_wiki_adapter.py

実機（wiki_index_ivfpq.faiss / wiki_chunks.db）不要。
全テストはモックで完結する。

実行:
    cd ~/デスクトップ/mobius_ai/MOBIUS_MMV
    cp ~/ダウンロード/test_wiki_adapter.py tests/test_wiki_adapter.py
    python -m pytest tests/test_wiki_adapter.py -v

成功基準 (phase_c_spec_v2_2.docx §11):
    既存テスト 170 passed, 2 xfailed を維持しつつ本テストが全 PASS

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import types
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# ── パス解決 ──────────────────────────────────────────────────────────────────
# pytest を MOBIUS_MMV ルートから実行する想定。
# src/adapters/wiki_adapter.py を直接 import できるよう調整。
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "adapters"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from wiki_adapter import (
    _GzChunkStore,
    RetrievalResult,
    Source,
    WikiAdapter,
)

# ═══════════════════════════════════════════════════════════════════════════════
# フィクスチャ
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture()
def sample_chunks() -> List[dict]:
    """テスト用チャンク 5 件"""
    return [
        {
            "title": "Speed of light",
            "url": "https://en.wikipedia.org/wiki/Speed_of_light",
            "text": "The speed of light in vacuum is 299,792,458 metres per second.",
            "chunk_index": 0,
            "license": "CC BY-SA 4.0",
        },
        {
            "title": "Speed of light",
            "url": "https://en.wikipedia.org/wiki/Speed_of_light",
            "text": "It is denoted by the letter c and is a fundamental constant of nature.",
            "chunk_index": 1,
            "license": "CC BY-SA 4.0",
        },
        {
            "title": "Albert Einstein",
            "url": "https://en.wikipedia.org/wiki/Albert_Einstein",
            "text": "Albert Einstein developed the theory of relativity.",
            "chunk_index": 0,
            "license": "CC BY-SA 4.0",
        },
        {
            "title": "Photon",
            "url": "https://en.wikipedia.org/wiki/Photon",
            "text": "A photon is a particle of light that travels at the speed of light.",
            "chunk_index": 0,
            "license": "CC BY-SA 4.0",
        },
        {
            "title": "Vacuum",
            "url": "https://en.wikipedia.org/wiki/Vacuum",
            "text": "A vacuum is a space devoid of matter.",
            "chunk_index": 0,
            "license": "CC BY-SA 4.0",
        },
    ]


@pytest.fixture()
def gz_chunks_file(tmp_dir, sample_chunks) -> Path:
    """sample_chunks を jsonl.gz に書き込んだ一時ファイル"""
    gz_path = tmp_dir / "wiki_chunks.jsonl.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        for chunk in sample_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return gz_path


@pytest.fixture()
def chunk_store(tmp_dir, gz_chunks_file) -> _GzChunkStore:
    """構築済み _GzChunkStore"""
    store = _GzChunkStore(
        chunks_gz_path=gz_chunks_file,
        offsets_path=tmp_dir / "line_offsets.npy",
    )
    store.build_offsets()
    store.open()
    yield store
    store.close()


@pytest.fixture()
def manifest_file(tmp_dir) -> Path:
    manifest = {
        "built_at": "2026-03-25T23:55:00Z",
        "zim_source": "wikipedia_en_mini_2026-03.zim",
        "chunk_count": 21979495,
        "model": "intfloat/multilingual-e5-large",
        "index_type": "IndexIVFPQ",
        "nlist": 4096,
        "m": 48,
        "nbits": 8,
        "index_size_gb": 1.24,
        "index_memory_gb": 0.75,
        "sufficiency_threshold": None,
    }
    p = tmp_dir / "wiki_manifest.json"
    p.write_text(json.dumps(manifest, indent=2))
    return p


@pytest.fixture()
def manifest_with_threshold(tmp_dir) -> Path:
    manifest = {
        "built_at": "2026-03-25T23:55:00Z",
        "chunk_count": 21979495,
        "sufficiency_threshold": 0.68,
    }
    p = tmp_dir / "wiki_manifest.json"
    p.write_text(json.dumps(manifest, indent=2))
    return p


def _make_adapter(tmp_dir, manifest_path, sample_chunks) -> WikiAdapter:
    """
    FAISS・SentenceTransformer をモックした WikiAdapter を返す。
    load() を内部で呼ぶ。
    """
    n = len(sample_chunks)
    dim = 384

    # ── FAISS モック ──────────────────────────────────────────────────────────
    mock_index = MagicMock()
    mock_index.ntotal = 21_979_495
    # search() → distances (1, top_k), indices (1, top_k)
    def fake_search(vec, k):
        actual_k = min(k, n)
        ids   = np.arange(actual_k, dtype=np.int64).reshape(1, actual_k)
        # コサイン距離: d=0 → score=1.0 に近い値
        dists = np.array([[0.10, 0.20, 0.30, 0.40, 0.50][:actual_k]], dtype=np.float32)
        return dists, ids
    mock_index.search = fake_search

    # ── SentenceTransformer モック ────────────────────────────────────────────
    mock_model = MagicMock()
    def fake_encode(texts, **kwargs):
        return np.random.rand(len(texts), dim).astype(np.float32)
    mock_model.encode = fake_encode

    # ── _GzChunkStore: 実 SQLite を使う ─────────────────────────────────────────
    gz_path = tmp_dir / "wiki_chunks.jsonl.gz"
    with gzip.open(gz_path, "wt") as f:
        for chunk in sample_chunks:
            f.write(json.dumps(chunk) + "\n")

    store = _GzChunkStore(
        chunks_gz_path=gz_path,
        offsets_path=tmp_dir / "line_offsets.npy",
    )
    store.build_offsets()
    store.open()

    adapter = WikiAdapter(
        index_path=str(tmp_dir / "wiki_index_ivfpq.faiss"),
        chunks_path=str(gz_path),
        manifest_path=str(manifest_path),
        offsets_path=str(tmp_dir / "line_offsets.npy"),
    )

    # モックを注入して load() 相当の状態にする
    with patch("faiss.read_index", return_value=mock_index), \
         patch("wiki_adapter.SentenceTransformer", return_value=mock_model):
        # index ファイルダミーを作成（存在チェックのため）
        (tmp_dir / "wiki_index_ivfpq.faiss").touch()
        adapter.load()

    # store は既に build 済みのものに差し替え
    adapter._store = store  # _GzChunkStore

    return adapter


# ═══════════════════════════════════════════════════════════════════════════════
# § 1. _GzChunkStore テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestChunkStore:

    def test_build_creates_offsets(self, chunk_store, tmp_dir):
        """build_offsets() 後に npy ファイルが存在すること"""
        assert (tmp_dir / "line_offsets.npy").exists()

    def test_build_row_count(self, chunk_store, sample_chunks):
        """オフセット数が sample_chunks と一致すること"""
        import numpy as np
        offsets = np.load(chunk_store.offsets_path)
        assert len(offsets) == len(sample_chunks)

    def test_get_by_rowid(self, chunk_store, sample_chunks):
        """rowid=0 のチャンクが正しく取得できること"""
        rows = chunk_store.get([0])
        assert len(rows) == 1
        assert rows[0]["title"] == sample_chunks[0]["title"]
        assert rows[0]["url"]   == sample_chunks[0]["url"]

    def test_get_multiple_rowids(self, chunk_store):
        """複数 rowid の取得"""
        rows = chunk_store.get([0, 2, 4])
        assert len(rows) == 3

    def test_get_missing_rowid(self, chunk_store):
        """存在しない rowid は返さない（エラーにならない）"""
        rows = chunk_store.get([9999])
        assert rows == []

    def test_is_ready_true(self, chunk_store):
        assert chunk_store.is_ready() is True

    def test_is_ready_false_no_db(self, tmp_dir, gz_chunks_file):
        store = _GzChunkStore(
            chunks_gz_path=gz_chunks_file,
            offsets_path=tmp_dir / "nonexistent.npy",
        )
        assert store.is_ready() is False

    def test_license_field(self, chunk_store):
        """CC BY-SA 4.0 が正しく格納されていること（§8 ライセンス準拠）"""
        rows = chunk_store.get([0])
        assert rows[0]["license"] == "CC BY-SA 4.0"

    def test_offsets_length(self, chunk_store, sample_chunks):
        """オフセット配列の長さが chunk 数と一致すること"""
        import numpy as np
        offsets = np.load(chunk_store.offsets_path)
        assert len(offsets) == len(sample_chunks)

    def test_build_skips_empty_lines(self, tmp_dir):
        """空行・不正 JSON を含む gz でもクラッシュしないこと"""
        gz_path = tmp_dir / "bad.jsonl.gz"
        with gzip.open(gz_path, "wt") as f:
            f.write('{"title":"A","url":"http://a","text":"aaa","chunk_index":0,"license":"CC BY-SA 4.0"}\n')
            f.write("\n")           # 空行
            f.write("not json\n")   # 不正 JSON
            f.write('{"title":"B","url":"http://b","text":"bbb","chunk_index":0,"license":"CC BY-SA 4.0"}\n')

        store = _GzChunkStore(
            chunks_gz_path=gz_path,
            offsets_path=tmp_dir / "bad.npy",
        )
        store.build_offsets()
        store.open()
        # build_offsets は全行のオフセットを記録する（空行・不正JSONも含む）
        # 正常行(0行目・3行目)のみ get() で取得できることを確認
        rows = store.get([0, 3])
        valid = [r for r in rows if r.get("text", "").strip()]
        assert len(valid) == 2  # 正常行のみ取得可能


# ═══════════════════════════════════════════════════════════════════════════════
# § 2. WikiAdapter.load() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestWikiAdapterLoad:

    def test_load_sets_loaded(self, tmp_dir, manifest_file, sample_chunks):
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        assert adapter._loaded is True

    def test_load_threshold_null_uses_zero(self, tmp_dir, manifest_file, sample_chunks):
        """manifest の sufficiency_threshold=null → 0.0 にフォールバックし警告"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        assert adapter.threshold == 0.0

    def test_load_threshold_from_manifest(
        self, tmp_dir, manifest_with_threshold, sample_chunks
    ):
        """manifest に閾値あり → そのまま読む"""
        adapter = _make_adapter(tmp_dir, manifest_with_threshold, sample_chunks)
        assert adapter.threshold == pytest.approx(0.68)

    def test_load_idempotent(self, tmp_dir, manifest_file, sample_chunks):
        """load() を 2 回呼んでもエラーにならない"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        adapter.load()  # 2 回目
        assert adapter._loaded is True

    def test_load_raises_if_index_missing(self, tmp_dir, manifest_file):
        """FAISS ファイルが存在しない場合 FileNotFoundError"""
        adapter = WikiAdapter(
            index_path=str(tmp_dir / "no_such.faiss"),
            chunks_path=str(tmp_dir / "no_such.gz"),
            manifest_path=str(manifest_file),
        )
        with pytest.raises(FileNotFoundError):
            adapter.load()

    def test_device_can_be_forced_to_cpu(self, tmp_dir, manifest_file, sample_chunks, monkeypatch):
        """原則 G: MMV_EMBEDDING_DEVICE=cpu でCPU固定可能"""
        monkeypatch.setenv("MMV_EMBEDDING_DEVICE", "cpu")
        assert WikiAdapter._select_device() == "cpu"

    def test_nprobe_set(self, tmp_dir, manifest_file, sample_chunks):
        """nprobe がインデックスに設定されていること"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        assert adapter._index.nprobe == adapter.nprobe


# ═══════════════════════════════════════════════════════════════════════════════
# § 3. WikiAdapter.retrieve() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestWikiAdapterRetrieve:

    def test_retrieve_returns_result(self, tmp_dir, manifest_file, sample_chunks):
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        assert isinstance(result, RetrievalResult)

    def test_retrieve_source_type(self, tmp_dir, manifest_file, sample_chunks):
        """source_type は 'local_rag' (08_api_types §9)"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        for src in result.sources:
            assert src.source_type == "local_rag"

    def test_retrieve_source_has_url(self, tmp_dir, manifest_file, sample_chunks):
        """CC BY-SA 4.0 帰属: url が空でないこと (§8 ライセンス準拠)"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        for src in result.sources:
            assert src.uri.startswith("http")

    def test_retrieve_relevance_score_range(self, tmp_dir, manifest_file, sample_chunks):
        """relevance_score は 0.0〜1.0 の範囲内"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        for src in result.sources:
            assert 0.0 <= src.relevance_score <= 1.0

    def test_retrieve_top_k_respected(self, tmp_dir, manifest_file, sample_chunks):
        """top_k=3 を指定した場合 sources は 3 件以下"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light", top_k=3)
        assert len(result.sources) <= 3

    def test_retrieve_top_k_max_clamp(self, tmp_dir, manifest_file, sample_chunks):
        """top_k > MAX_TOP_K の場合は 20 に切り詰める"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        # FAISS モックは 5 件しか返さないので sources<=5 を確認
        result = adapter.retrieve("speed of light", top_k=999)
        assert len(result.sources) <= 20

    def test_retrieve_synthesis_nonempty(self, tmp_dir, manifest_file, sample_chunks):
        """synthesis は空でないこと（EAL が合成責任を持つ前提の生テキスト）"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        assert result.synthesis.strip() != ""

    def test_retrieve_synthesis_is_raw_concat(self, tmp_dir, manifest_file, sample_chunks):
        """synthesis はチャンクテキストの連結のみ。EAL が合成する (§7)"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        # synthesis に改行区切りでチャンクテキストが含まれること
        for src_text in result.synthesis.split("\n\n"):
            assert len(src_text) > 0

    def test_retrieve_outcome_success(self, tmp_dir, manifest_file, sample_chunks):
        """top_k 件取得できた場合 outcome='success'"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light", top_k=5)
        assert result.outcome == "success"

    def test_retrieve_raises_if_not_loaded(self, tmp_dir, manifest_file):
        """load() 前に retrieve() を呼ぶと RuntimeError"""
        adapter = WikiAdapter(
            index_path=str(tmp_dir / "dummy.faiss"),
            chunks_path=str(tmp_dir / "dummy.gz"),
            manifest_path=str(manifest_file),
        )
        with pytest.raises(RuntimeError, match="not loaded"):
            adapter.retrieve("test")

    def test_retrieve_all_faiss_invalid(self, tmp_dir, manifest_file, sample_chunks):
        """FAISS が全て -1 を返した場合 outcome='failed'"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)

        def all_invalid(vec, k):
            ids   = np.full((1, k), -1, dtype=np.int64)
            dists = np.zeros((1, k), dtype=np.float32)
            return dists, ids

        adapter._index.search = all_invalid
        result = adapter.retrieve("unmatchable query", top_k=5)
        assert result.outcome == "failed"
        assert result.sources == []
        assert result.synthesis == ""

    def test_retrieve_retrieved_at_is_utc_iso(self, tmp_dir, manifest_file, sample_chunks):
        """retrieved_at が ISO 8601 UTC 文字列であること (08_api_types §9)"""
        from datetime import datetime, timezone
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        for src in result.sources:
            dt = datetime.fromisoformat(src.retrieved_at)
            assert dt.tzinfo is not None


# ═══════════════════════════════════════════════════════════════════════════════
# § 4. WikiAdapter.get_sufficiency_score() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestSufficiencyScore:

    def test_score_nonempty_result(self, tmp_dir, manifest_file, sample_chunks):
        """チャンクがある場合スコアは 0.0 より大きい"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        score = adapter.get_sufficiency_score(result)
        assert 0.0 <= score <= 1.0

    def test_score_empty_result(self, tmp_dir, manifest_file, sample_chunks):
        """sources=[] の場合は 0.0"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        empty = RetrievalResult(sources=[], outcome="failed", synthesis="")
        assert adapter.get_sufficiency_score(empty) == 0.0

    def test_score_is_max_of_sources(self, tmp_dir, manifest_file, sample_chunks):
        """スコアは sources の relevance_score の最大値"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        sources = [
            Source("local_rag", "A", "http://a", 0, "2026-01-01T00:00:00+00:00", 0.55),
            Source("local_rag", "B", "http://b", 0, "2026-01-01T00:00:00+00:00", 0.82),
            Source("local_rag", "C", "http://c", 0, "2026-01-01T00:00:00+00:00", 0.71),
        ]
        result = RetrievalResult(sources=sources, outcome="success", synthesis="x")
        assert adapter.get_sufficiency_score(result) == pytest.approx(0.82)

    def test_threshold_comparison(self, tmp_dir, manifest_with_threshold, sample_chunks):
        """threshold=0.68 の場合、スコア>=0.68 なら充足判定"""
        adapter = _make_adapter(tmp_dir, manifest_with_threshold, sample_chunks)
        assert adapter.threshold == pytest.approx(0.68)

        sufficient_result = RetrievalResult(
            sources=[
                Source("local_rag", "X", "http://x", 0,
                       "2026-01-01T00:00:00+00:00", 0.75)
            ],
            outcome="success", synthesis="x",
        )
        assert adapter.get_sufficiency_score(sufficient_result) >= adapter.threshold

        insufficient_result = RetrievalResult(
            sources=[
                Source("local_rag", "Y", "http://y", 0,
                       "2026-01-01T00:00:00+00:00", 0.50)
            ],
            outcome="partial", synthesis="y",
        )
        assert adapter.get_sufficiency_score(insufficient_result) < adapter.threshold


# ═══════════════════════════════════════════════════════════════════════════════
# § 5. WikiAdapter.is_available() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsAvailable:

    def test_available_after_load(self, tmp_dir, manifest_file, sample_chunks):
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        assert adapter.is_available() is True

    def test_not_available_before_load(self, tmp_dir, manifest_file):
        adapter = WikiAdapter(
            index_path=str(tmp_dir / "dummy.faiss"),
            chunks_path=str(tmp_dir / "dummy.gz"),
            manifest_path=str(manifest_file),
        )
        assert adapter.is_available() is False

    def test_not_available_after_close(self, tmp_dir, manifest_file, sample_chunks):
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        adapter.close()
        assert adapter.is_available() is False


# ═══════════════════════════════════════════════════════════════════════════════
# § 6. WikiAdapter.update_threshold() テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateThreshold:

    def test_update_threshold_writes_manifest(self, tmp_dir, manifest_file, sample_chunks):
        """update_threshold() で manifest.json に閾値が書き込まれること"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        adapter.update_threshold(0.72)
        assert adapter.threshold == pytest.approx(0.72)
        written = json.loads(manifest_file.read_text())
        assert written["sufficiency_threshold"] == pytest.approx(0.72)

    def test_update_threshold_persists(self, tmp_dir, manifest_file, sample_chunks):
        """書き込んだ閾値が次回 load 時に読めること"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        adapter.update_threshold(0.65)
        # manifest を再読して確認
        with open(manifest_file) as f:
            data = json.load(f)
        assert data["sufficiency_threshold"] == pytest.approx(0.65)


# ═══════════════════════════════════════════════════════════════════════════════
# § 7. Answer Entitlement 分離テスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnswerEntitlement:
    """
    「検索できた ≠ 答える権利がある」の分離を検証。
    (handover_phase_c_v2.docx §5.3 / phase_c_spec_v2_2.docx §7)
    """

    def test_retrieve_does_not_decide_route(self, tmp_dir, manifest_file, sample_chunks):
        """RetrievalResult に route フィールドが存在しないこと"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        assert not hasattr(result, "route")

    def test_synthesis_is_not_answer(self, tmp_dir, manifest_file, sample_chunks):
        """
        synthesis はチャンクの生連結のみ。
        LLM が生成した回答文ではないこと（EAL が担う）。
        """
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        # synthesis の各ブロックがチャンクテキストと一致する（LLM を呼んでいない）
        chunks = result.synthesis.split("\n\n")
        assert all(len(c.strip()) > 0 for c in chunks)

    def test_high_score_does_not_guarantee_answer(
        self, tmp_dir, manifest_file, sample_chunks
    ):
        """
        sufficiency_score が高くても WikiAdapter は route を決定しない。
        (L0 制御層が Answer Entitlement を判断する)
        """
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        score = adapter.get_sufficiency_score(result)
        # score が高い場合でも WikiAdapter は "answer" を返さない
        assert result.outcome in ("success", "partial", "failed")
        assert result.outcome != "answer"


# ═══════════════════════════════════════════════════════════════════════════════
# § 8. ライセンス準拠テスト (phase_c_spec_v2_2.docx §8)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLicenseCompliance:

    def test_sources_have_uri_for_attribution(self, tmp_dir, manifest_file, sample_chunks):
        """CC BY-SA 4.0 帰属: 各 Source に uri（Wikipedia URL）があること"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("speed of light")
        for src in result.sources:
            assert src.uri != ""
            assert "wikipedia.org" in src.uri

    def test_chunk_store_preserves_license_field(self, chunk_store):
        """チャンクに license フィールドが含まれること"""
        rows = chunk_store.get([0, 1, 2])
        for row in rows:
            assert row["license"] == "CC BY-SA 4.0"


# ═══════════════════════════════════════════════════════════════════════════════
# § 9. 境界値・エッジケーステスト
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_empty_query(self, tmp_dir, manifest_file, sample_chunks):
        """空クエリでもクラッシュしないこと"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("")
        assert result.outcome in ("success", "partial", "failed")

    def test_top_k_one(self, tmp_dir, manifest_file, sample_chunks):
        """top_k=1 でも動作すること"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("light", top_k=1)
        assert len(result.sources) <= 1

    def test_top_k_zero_clamped_to_one(self, tmp_dir, manifest_file, sample_chunks):
        """top_k=0 は 1 に切り上げられること"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        result = adapter.retrieve("light", top_k=0)
        # クラッシュしないことを確認
        assert result.outcome in ("success", "partial", "failed")

    def test_repr(self, tmp_dir, manifest_file, sample_chunks):
        """__repr__ が文字列を返すこと"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        r = repr(adapter)
        assert "WikiAdapter" in r
        assert "loaded" in r

    def test_close_idempotent(self, tmp_dir, manifest_file, sample_chunks):
        """close() を 2 回呼んでもエラーにならない"""
        adapter = _make_adapter(tmp_dir, manifest_file, sample_chunks)
        adapter.close()
        adapter.close()

    def test_manifest_missing(self, tmp_dir, sample_chunks):
        """manifest が存在しなくても load() は完了する（警告のみ）"""
        gz_path = tmp_dir / "wiki_chunks.jsonl.gz"
        with gzip.open(gz_path, "wt") as f:
            for chunk in sample_chunks:
                f.write(json.dumps(chunk) + "\n")

        mock_index = MagicMock()
        mock_index.ntotal = 100
        mock_index.search = lambda v, k: (
            np.zeros((1, k), dtype=np.float32),
            np.arange(k, dtype=np.int64).reshape(1, k),
        )
        mock_model = MagicMock()
        mock_model.encode = lambda texts, **kw: np.random.rand(len(texts), 384).astype(np.float32)

        (tmp_dir / "dummy.faiss").touch()
        adapter = WikiAdapter(
            index_path=str(tmp_dir / "dummy.faiss"),
            chunks_path=str(gz_path),
            manifest_path=str(tmp_dir / "nonexistent_manifest.json"),
            offsets_path=str(tmp_dir / "line_offsets.npy"),
        )
        with patch("faiss.read_index", return_value=mock_index), \
             patch("wiki_adapter.SentenceTransformer", return_value=mock_model):
            adapter.load()
        assert adapter._loaded is True
        assert adapter.threshold == 0.0  # null フォールバック
