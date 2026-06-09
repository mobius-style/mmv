#!/usr/bin/env python3
"""
calibrate_threshold.py — Phase C.5: Box B sufficiency threshold 実測・較正
scripts/calibrate_threshold.py

wiki_index_ivfpq.faiss（実機）を使って sufficiency_threshold を実測し、
wiki_manifest.json に書き込む。

実行:
    cd ~/デスクトップ/mobius_ai/MOBIUS_MMV
    cp ~/ダウンロード/calibrate_threshold.py scripts/calibrate_threshold.py
    mobius
    python scripts/calibrate_threshold.py

出力:
    data/box_b/wiki_manifest.json の sufficiency_threshold が更新される
    logs/calibration_YYYYMMDD_HHMMSS.json に詳細ログが保存される

成功基準 (phase_c_spec_v2_2.docx §11):
    recall@5 ≥ 90% (IndexFlatIP 比)
    threshold 決定後、test_wiki_adapter.py が全 PASS

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# パス解決（MOBIUS_MMV ルートから実行前提）
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "adapters"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from wiki_adapter import WikiAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── 較正クエリセット ──────────────────────────────────────────────────────────
# B15/A19 評価と重複しない英語クエリ。
# Wikipedia に対して「答えが存在する」ことが明確な質問を選定。
# 目的: IndexIVFPQ のスコア分布を実測し、
#       「関連チャンクあり」と「関連チャンクなし」の境界を決定する。

CALIBRATION_QUERIES = [
    # § 高関連性が期待されるクエリ（True Positive 候補）
    {"query": "What is the speed of light?",              "expect": "relevant"},
    {"query": "Who developed the theory of relativity?",  "expect": "relevant"},
    {"query": "What is the capital of France?",           "expect": "relevant"},
    {"query": "How does photosynthesis work?",            "expect": "relevant"},
    {"query": "What is DNA?",                             "expect": "relevant"},
    {"query": "Who wrote Hamlet?",                        "expect": "relevant"},
    {"query": "What is the boiling point of water?",      "expect": "relevant"},
    {"query": "When did World War II end?",               "expect": "relevant"},
    {"query": "What is the Pythagorean theorem?",         "expect": "relevant"},
    {"query": "Who invented the telephone?",              "expect": "relevant"},
    {"query": "What is the largest planet in the solar system?", "expect": "relevant"},
    {"query": "What is machine learning?",                "expect": "relevant"},
    {"query": "What is the French Revolution?",           "expect": "relevant"},
    {"query": "Who is Nikola Tesla?",                     "expect": "relevant"},
    {"query": "What is quantum mechanics?",               "expect": "relevant"},
    # § 低関連性が期待されるクエリ（False Positive 抑制用）
    {"query": "xkj9f3m2 nonsense string",                "expect": "irrelevant"},
    {"query": "aaaa bbbb cccc dddd eeee ffff",           "expect": "irrelevant"},
    {"query": "zzzz yyyy xxxx wwww",                     "expect": "irrelevant"},
    {"query": "!@#$%^&*() special chars",               "expect": "irrelevant"},
    {"query": "asdfqwer zxcvpoiu mnbvlkjh",             "expect": "irrelevant"},
]

TOP_K = 5
PERCENTILE_TP = 10   # True Positive 群の下位 10 パーセンタイル
PERCENTILE_FP = 90   # False Positive 群の上位 90 パーセンタイル


def run_calibration(
    adapter: WikiAdapter,
    queries: list[dict],
    top_k: int = TOP_K,
) -> dict:
    """
    較正クエリを全件検索し、スコア分布を計測する。

    Returns:
        {
            "tp_scores":   [float, ...],  # True Positive クエリの max スコア一覧
            "fp_scores":   [float, ...],  # Irrelevant クエリの max スコア一覧
            "per_query":   [dict, ...],   # クエリごとの詳細
        }
    """
    tp_scores: list[float] = []
    fp_scores: list[float] = []
    per_query: list[dict]  = []

    logger.info(f"Running calibration: {len(queries)} queries, top_k={top_k}")

    for i, item in enumerate(queries, 1):
        query  = item["query"]
        expect = item["expect"]

        t0     = time.time()
        result = adapter.retrieve(query, top_k=top_k)
        score  = adapter.get_sufficiency_score(result)
        ms     = (time.time() - t0) * 1000

        per_query.append({
            "query":    query,
            "expect":   expect,
            "score":    round(score, 4),
            "outcome":  result.outcome,
            "sources":  len(result.sources),
            "latency_ms": round(ms, 1),
            "top_sources": [
                {"label": s.label, "score": s.relevance_score}
                for s in result.sources[:3]
            ],
        })

        if expect == "relevant":
            tp_scores.append(score)
        else:
            fp_scores.append(score)

        logger.info(
            f"  [{i:02d}/{len(queries)}] {expect:10s} "
            f"score={score:.4f} latency={ms:.0f}ms  {query[:50]}"
        )

    return {
        "tp_scores": tp_scores,
        "fp_scores": fp_scores,
        "per_query": per_query,
    }


def decide_threshold(tp_scores: list[float], fp_scores: list[float]) -> dict:
    """
    TP・FP スコア分布から sufficiency_threshold を決定する。

    戦略:
        threshold = max(
            tp_10th_percentile * 0.95,  # TP を取りこぼさない（再現率重視）
            fp_90th_percentile,         # FP を通さない（精度確保）
        ) の中間点

        ただし TP 群が FP 群より明確に高い場合は
        tp_10th と fp_90th の中点を採用する。

    Returns:
        {
            "threshold":        float,
            "tp_10th":          float,
            "fp_90th":          float,
            "tp_mean":          float,
            "fp_mean":          float,
            "separation_ok":    bool,   # TP > FP の分離ができているか
            "recall_estimated": float,  # 暫定 recall@5 推定値
        }
    """
    tp = np.array(tp_scores)
    fp = np.array(fp_scores) if fp_scores else np.array([0.0])

    tp_10th = float(np.percentile(tp, PERCENTILE_TP))
    fp_90th = float(np.percentile(fp, PERCENTILE_FP))
    tp_mean = float(np.mean(tp))
    fp_mean = float(np.mean(fp))

    separation_ok = tp_10th > fp_90th

    if separation_ok:
        # TP と FP が明確に分離 → 中点を採用
        threshold = round((tp_10th + fp_90th) / 2.0, 4)
    else:
        # 分離不十分 → TP の下位 10 パーセンタイルを保守的に採用
        logger.warning(
            f"TP/FP separation is poor: tp_10th={tp_10th:.4f} fp_90th={fp_90th:.4f}. "
            "Using tp_10th as conservative threshold."
        )
        threshold = round(tp_10th * 0.95, 4)

    # recall@5 暫定推定 (threshold 以上の TP 割合)
    recall_est = float(np.mean(tp >= threshold))

    return {
        "threshold":        threshold,
        "tp_10th":          round(tp_10th, 4),
        "fp_90th":          round(fp_90th, 4),
        "tp_mean":          round(tp_mean, 4),
        "fp_mean":          round(fp_mean, 4),
        "separation_ok":    separation_ok,
        "recall_estimated": round(recall_est, 4),
    }


def check_recall_vs_flatip(adapter: WikiAdapter, n_samples: int = 50) -> dict:
    """
    IndexIVFPQ vs IndexFlatIP の recall@5 を比較。
    (phase_c_spec_v2_2.docx §11 成功基準: recall@5 ≥ 90%)

    FlatIP インデックスが存在する場合のみ実行。
    存在しない場合はスキップ（実機で build 済みの場合に使用）。

    Returns:
        {"recall_at_5": float, "skipped": bool}
    """
    import faiss

    flat_path = Path(adapter.index_path).parent / "wiki_index_flatip.faiss"
    if not flat_path.exists():
        logger.warning(
            f"[recall@5] FlatIP index not found: {flat_path}. "
            "Skipping recall measurement. "
            "Build with: python scripts/build_flatip_sample.py"
        )
        return {"recall_at_5": None, "skipped": True}

    logger.info(f"[recall@5] Loading FlatIP index: {flat_path}")
    flat_index = faiss.read_index(str(flat_path))

    sample_queries = [
        "speed of light", "Einstein relativity", "DNA structure",
        "quantum mechanics", "French Revolution",
        "photosynthesis", "World War II", "Pythagorean theorem",
        "machine learning neural network", "black hole event horizon",
    ][:n_samples]

    hits = 0
    total = 0

    for q in sample_queries:
        vec = adapter._model.encode(
            [q], convert_to_numpy=True, normalize_embeddings=True
        ).astype(np.float32)

        _, ivfpq_ids = adapter._index.search(vec, TOP_K)
        _, flat_ids  = flat_index.search(vec, TOP_K)

        ivfpq_set = set(ivfpq_ids[0][ivfpq_ids[0] >= 0].tolist())
        flat_set  = set(flat_ids[0][flat_ids[0] >= 0].tolist())

        overlap = len(ivfpq_set & flat_set)
        hits   += overlap
        total  += len(flat_set)

    recall = hits / total if total > 0 else 0.0
    logger.info(f"[recall@5] {recall:.1%} ({hits}/{total})")

    return {"recall_at_5": round(recall, 4), "skipped": False}


def main():
    parser = argparse.ArgumentParser(
        description="Phase C.5: Box B sufficiency threshold 較正"
    )
    parser.add_argument(
        "--index",    default="data/box_b/wiki_index_ivfpq.faiss"
    )
    parser.add_argument(
        "--chunks",   default="data/box_b/wiki_chunks.jsonl.gz"
    )
    parser.add_argument(
        "--manifest", default="data/box_b/wiki_manifest.json"
    )
    parser.add_argument(
        "--logs-dir", default="logs"
    )
    parser.add_argument(
        "--top-k", type=int, default=TOP_K
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="threshold を計算するが manifest には書き込まない"
    )
    parser.add_argument(
        "--skip-recall", action="store_true",
        help="recall@5 測定をスキップ（FlatIP index がない場合）"
    )
    args = parser.parse_args()

    # ── 1. アダプタ起動 ───────────────────────────────────────────────────────
    adapter = WikiAdapter(
        index_path   = args.index,
        chunks_path  = args.chunks,
        manifest_path = args.manifest,
    )
    logger.info("[calibrate] Loading WikiAdapter...")
    adapter.load()
    logger.info(f"[calibrate] {adapter}")

    # ── 2. 較正クエリ実行 ─────────────────────────────────────────────────────
    calib = run_calibration(adapter, CALIBRATION_QUERIES, top_k=args.top_k)

    # ── 3. 閾値決定 ───────────────────────────────────────────────────────────
    decision = decide_threshold(calib["tp_scores"], calib["fp_scores"])

    logger.info("=" * 60)
    logger.info(f"  tp_mean    : {decision['tp_mean']:.4f}")
    logger.info(f"  fp_mean    : {decision['fp_mean']:.4f}")
    logger.info(f"  tp_10th    : {decision['tp_10th']:.4f}")
    logger.info(f"  fp_90th    : {decision['fp_90th']:.4f}")
    logger.info(f"  separation : {'OK' if decision['separation_ok'] else 'NG ⚠'}")
    logger.info(f"  → threshold: {decision['threshold']:.4f}")
    logger.info(f"  recall_est : {decision['recall_estimated']:.1%}")
    logger.info("=" * 60)

    # ── 4. recall@5 測定（FlatIP が存在する場合）─────────────────────────────
    recall_result = {"recall_at_5": None, "skipped": True}
    if not args.skip_recall:
        recall_result = check_recall_vs_flatip(adapter)
        if not recall_result["skipped"]:
            r = recall_result["recall_at_5"]
            if r < 0.90:
                logger.warning(
                    f"[recall@5] {r:.1%} < 90% 目標未達。"
                    "nprobe を増やすか FlatIP へのダウングレードを検討してください。"
                )
            else:
                logger.info(f"[recall@5] {r:.1%} ≥ 90% ✅")

    # ── 5. 結果をログ保存 ─────────────────────────────────────────────────────
    log_dir = Path(args.logs_dir)
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"calibration_{ts}.json"

    log_data = {
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "index_path": args.index,
        "top_k": args.top_k,
        "decision": decision,
        "recall": recall_result,
        "per_query": calib["per_query"],
    }
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))
    logger.info(f"[calibrate] Log saved: {log_path}")

    # ── 6. manifest 更新 ──────────────────────────────────────────────────────
    if args.dry_run:
        logger.info(f"[calibrate] --dry-run: manifest は更新しません。")
        logger.info(f"  本番適用する場合: --dry-run を外して再実行してください。")
    else:
        adapter.update_threshold(decision["threshold"])
        logger.info(
            f"[calibrate] ✅ sufficiency_threshold = {decision['threshold']:.4f} "
            f"→ {args.manifest}"
        )

    # ── 7. 結果サマリ表示 ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Phase C.5 較正結果")
    print("=" * 60)
    print(f"  threshold      : {decision['threshold']:.4f}")
    print(f"  separation     : {'OK ✅' if decision['separation_ok'] else 'NG ⚠️  (要手動確認)'}")
    print(f"  recall_est     : {decision['recall_estimated']:.1%}")
    if not recall_result["skipped"]:
        r5 = recall_result["recall_at_5"]
        mark = "✅" if r5 >= 0.90 else "⚠️ "
        print(f"  recall@5 vs FlatIP: {r5:.1%} {mark}")
    else:
        print(f"  recall@5       : スキップ（FlatIP index なし）")
    print(f"  log            : {log_path}")
    if not args.dry_run:
        print(f"  manifest       : {args.manifest} 更新済み ✅")
    else:
        print(f"  manifest       : 未更新 (--dry-run)")
    print("=" * 60)

    # ── 8. 次のアクション案内 ─────────────────────────────────────────────────
    print("\n次のステップ:")
    if args.dry_run:
        print(f"  python scripts/calibrate_threshold.py  # --dry-run を外して本適用")
    else:
        print(f"  python -m pytest tests/test_wiki_adapter.py -v  # 全テスト PASS を確認")
        print(f"  # → Box B 完走 ✅ → custom_rag_adapter.py (Box A) へ")


if __name__ == "__main__":
    main()
