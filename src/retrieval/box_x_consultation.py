"""
box_x_consultation.py — Narrow, bounded Box X runtime consultation.

Box X is the curated external durable knowledge layer. In this pass
we add a **conservative** consultation helper that callers (e.g. the
existing retrieval stack) can invoke to check whether Box X carries a
relevant curated entry for a given query.

Design principles:
  - Box X is consulted ONLY when it is likely to help:
      * the query contains a known technical/reference token, OR
      * the query is explicitly flagged as reference-seeking
    Otherwise we skip with an inspectable note.
  - Consultation is pure (no mutations).
  - Never outranks hard invariants. Callers decide how to weigh Box X
    hits against Box 0 / Box A / Box W / Box S. This helper returns a
    candidate set plus inspectable notes, nothing more.
  - Empty store → no hit, no fake content.

This module is intentionally separate from ``WikiAdapter`` so that the
Box W purity invariant remains intact: Box W and Box X are distinct
retrieval layers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.memory.indexed_box_entry import (
    NOTE_BOX_X_CONSULTED,
    NOTE_BOX_X_HIT,
    NOTE_BOX_X_MISS,
    NOTE_BOX_X_REFERENCE_USED,
    NOTE_BOX_X_SKIPPED_LOW_CONFIDENCE,
    NOTE_BOX_X_SKIPPED_NONTECHNICAL,
)

logger = logging.getLogger(__name__)


# Minimum quality score for a Box X entry to be considered a viable
# candidate at consultation time. Entries below this are ignored.
_BOX_X_CONSULT_MIN_QUALITY = 0.60

# Narrow technical token list. Overlap with the failure classifier's
# list is intentional — these are the queries where Box X is most
# likely to carry curated material. Expansion should be deliberate.
_CONSULT_TECHNICAL_TOKENS: List[str] = [
    # Category theory
    "counit", "カウニット", "unit morphism", "ユニット射",
    "natural transformation", "自然変換",
    "kleisli", "クライスリ圏", "adjoint", "随伴", "functor", "関手",
    "monad", "モナド", "eilenberg", "アイレンベルグ",
    # Stage 7 — category theory extension
    "yoneda", "米田", "comonad", "コモナド",
    "limit", "colimit", "極限", "余極限",
    # Type theory
    "lambda calculus", "ラムダ計算", "type theory", "型理論",
    "dependent types",
    # Physics
    "schrödinger", "schrodinger", "シュレーディンガー",
    "schrödinger equation", "シュレーディンガー方程式",
    # Linear algebra
    "eigenvalue", "固有値", "eigenvector", "固有ベクトル",
    # ML
    "transformer", "トランスフォーマー", "backpropagation", "誤差逆伝播",
    # Stage 7 — ML core
    "attention mechanism", "attention", "注意機構",
    "cnn", "convolutional neural network", "畳み込みニューラルネットワーク",
    "gradient descent", "勾配降下法",
    "reinforcement learning", "強化学習",
    "neural network", "ニューラルネットワーク",
    # Generic mathematical
    "lie algebra", "リー代数", "tensor", "テンソル",
    # Stage 7 — CS / algorithms
    "turing machine", "チューリングマシン",
    "dynamic programming", "動的計画法",
    "kernel", "カーネル",
    "buffer", "バッファ",
    # Stage 8 — systems / OS
    "process", "プロセス", "thread", "スレッド",
    "page fault", "ページフォールト", "system call", "syscall", "システムコール",
    "file system", "filesystem", "ファイルシステム", "ext4", "systemd",
    # Stage 8 — networking
    "tcp", "congestion control", "輻輳制御",
    "socket", "ソケット", "http", "dns",
    # Stage 8 — databases
    "database index", "db index", "インデックス",
    "transaction", "トランザクション", "acid",
    "database normalization", "正規化", "normal form",
    # Stage 8 — distributed systems
    "consensus", "paxos", "raft", "コンセンサス",
    "two-phase commit", "2pc", "2フェーズコミット",
    "consistency model", "整合性モデル", "一貫性モデル",
    "eventual consistency", "linearizab", "serializab",
    "replication", "レプリケーション",
    "cache", "キャッシュ",
    # Stage 8 — security
    "hash function", "ハッシュ関数", "cryptographic hash",
    "tls", "ssl", "public-key cryptography", "公開鍵暗号",
    # Stage 8 — compilers
    "compiler", "コンパイラ",
    "ssa", "static single assignment", "静的単一代入",
    "register allocation", "レジスタ割り当て",
    "compiler optimization", "コンパイラ最適化", "最適化手法",
    # Stage 8 — statistics / probability
    "bayes theorem", "bayes' theorem", "ベイズ", "bayesian",
    "probability distribution", "確率分布",
    "normal distribution", "gaussian distribution", "正規分布",
    "maximum likelihood", "最尤推定",
    "kernel density estimation", "カーネル密度推定",
    "markov chain", "マルコフ連鎖",
    # Stage 8 — ML advanced
    "batch normalization", "batchnorm", "バッチ正規化",
    "embedding", "埋め込み",
    "overfitting", "過学習",
    "saddle point", "鞍点",
    "activation function", "活性化関数", "relu", "sigmoid", "gelu",
    "loss function", "損失関数",
    # Stage 8 — math fundamentals
    "linear algebra", "線形代数",
    "gradient", "勾配",
]


# ── Stage 8 — domain disambiguation cues ──────────────────────────
#
# When Box X contains multiple entries for an ambiguous surface form
# (e.g. both "Kernel (operating system)" and "Kernel (mathematics/
# statistics)" match the token "kernel"), we apply a bounded score
# boost to the entry whose domain best matches nearby tokens in the
# query. Examples:
#
#   "kernel trick in SVM"           → ML/stats kernel wins
#   "linux kernel page tables"       → OS kernel wins
#   "buffer overflow in C"          → systems buffer wins
#   "image buffer for rendering"    → generic buffer (no OS bias)
#
# Each entry maps a domain label to a list of tokens whose presence
# in the query indicates that domain is the intended sense. Tokens
# are matched case-insensitively as substrings. The boost is
# bounded and never displaces the raw quality floor.
_DOMAIN_DISAMBIG_CUES: Dict[str, List[str]] = {
    # Operating systems / systems programming
    "operating systems": [
        "linux", "kernel space", "user space", "process", "thread",
        "syscall", "system call", "page table", "paging", "pid", "fork",
        "execve", "mmap", "cgroup", "systemd", "ext4", "btrfs", "xfs",
        "oom", "page fault", "scheduler", "init", "root", "sudo",
        "ファイルシステム", "カーネル空間", "ユーザ空間", "システムコール",
        "オペレーティングシステム", "os", "unix", "posix",
    ],
    # Networking
    "networking": [
        "tcp", "udp", "ip", "packet", "socket", "port", "http",
        "dns", "tls", "ssl", "rfc", "congestion", "ack", "syn", "fin",
        "mtu", "latency", "rtt", "bandwidth", "handshake", "quic",
        "パケット", "ソケット", "プロトコル", "通信", "ネットワーク",
    ],
    # Databases
    "databases": [
        "sql", "database", "table", "row", "column", "query", "index",
        "b-tree", "btree", "lsm", "transaction", "commit", "rollback",
        "schema", "foreign key", "primary key", "join", "acid",
        "isolation", "relation", "normalization", "normal form",
        "データベース", "インデックス", "スキーマ", "トランザクション",
    ],
    # Distributed systems
    "distributed systems": [
        "distributed", "replica", "replication", "leader", "follower",
        "consensus", "paxos", "raft", "2pc", "3pc", "quorum", "cap",
        "linearizab", "eventual consistency", "partition", "sharding",
        "分散", "コンセンサス", "レプリケーション",
    ],
    # Security
    "security": [
        "tls", "ssl", "cipher", "certificate", "x.509", "pki",
        "signature", "hash", "digest", "sha", "md5", "aes", "rsa", "ecc",
        "encrypt", "decrypt", "key exchange", "crypto", "cryptographic",
        "cryptography", "sign", "verify",
        "暗号", "署名", "鍵", "認証", "証明書",
    ],
    # Compilers
    "compilers": [
        "compile", "compiler", "compilation", "parser", "lexer", "ast",
        "llvm", "gcc", "clang", "optimization pass", "ir", "ssa",
        "register", "spill", "inline", "peephole",
        "コンパイラ", "最適化", "レジスタ", "中間表現",
    ],
    # Statistics / probability
    "statistics": [
        "probability", "distribution", "likelihood", "bayes", "prior",
        "posterior", "sample", "variance", "mean", "covariance",
        "gaussian", "pdf", "cdf", "mle", "em algorithm", "pca",
        "density", "estimator", "estimation", "statistic",
        "確率", "分布", "尤度", "ベイズ", "分散", "平均",
    ],
    "probability": [
        "probability", "random", "stochastic", "markov", "chain",
        "martingale", "poisson", "bernoulli",
        "確率", "マルコフ", "ランダム",
    ],
    # Machine learning
    "machine learning": [
        "neural", "network", "deep learning", "training", "gradient",
        "loss", "backprop", "backpropagation", "optimizer", "adam",
        "sgd", "batch", "epoch", "overfit", "regulariz", "dropout",
        "tensor", "feature", "model", "embedding", "svm", "kernel trick",
        "rbf", "transformer", "attention", "cnn", "rnn", "lstm",
        "reinforcement", "agent", "policy", "reward",
        "ニューラル", "学習", "訓練", "モデル", "特徴", "正則化",
        "深層学習", "機械学習",
    ],
    # Category theory
    "category theory": [
        "category", "functor", "natural transformation", "morphism",
        "monad", "comonad", "adjoint", "adjunction", "kleisli",
        "eilenberg", "yoneda", "limit", "colimit", "terminal",
        "initial", "cone", "cocone", "universal",
        "圏", "関手", "自然変換", "射", "モナド", "随伴",
    ],
    # Type theory
    "type theory": [
        "lambda", "lambda calculus", "type system", "dependent type",
        "curry-howard", "proposition", "inductive", "calculus of",
        "ラムダ", "型", "依存型",
    ],
    # Linear algebra / tensor / math
    "linear algebra": [
        "vector", "matrix", "matrices", "linear", "span", "basis",
        "orthogonal", "determinant", "rank", "null space", "row space",
        "column space", "svd", "qr decomposition", "diagonaliz",
        "ベクトル", "行列", "線形", "基底",
    ],
    "tensor mathematics": [
        "tensor", "multilinear", "rank", "contravariant", "covariant",
        "tensor product", "metric tensor", "riemannian",
        "テンソル", "多重線形", "計量",
    ],
    "mathematics": [
        "mathematical", "theorem", "proof", "derivative", "integral",
        "function", "limit", "continuity", "gradient", "jacobian",
        "数学", "定理", "証明", "微分", "積分", "勾配",
    ],
    # Quantum mechanics
    "quantum mechanics": [
        "quantum", "wave function", "hamiltonian", "hilbert",
        "eigenvalue", "observable", "operator", "spin", "entangle",
        "量子", "波動関数", "ハミルトニアン",
    ],
    # Optimization
    "optimization": [
        "minim", "maxim", "convex", "nonconvex", "saddle", "optim",
        "convergence", "hessian", "lagrang",
        "最適化", "凸", "非凸", "収束",
    ],
    # Algorithms / theory of computation
    "algorithms": [
        "algorithm", "complexity", "big-o", "o(n", "np-hard", "np-complete",
        "greedy", "divide and conquer", "dp", "dynamic programming",
        "graph", "tree", "sort", "search",
        "アルゴリズム", "計算量", "動的計画",
    ],
    "theory of computation": [
        "turing", "automaton", "finite state", "decidab", "computab",
        "halting", "complexity class",
        "チューリング", "オートマトン", "計算可能",
    ],
    # General CS (fallback for terms without strong domain cues)
    "computer science": [
        "cache", "memory", "buffer", "stack", "heap", "pointer",
        "register", "instruction", "assembly", "binary", "bit",
        "データ構造", "メモリ",
    ],
}

# Boost magnitudes for disambiguation. Bounded and additive to quality_score.
_DOMAIN_CUE_STRONG_BOOST = 0.12   # two or more domain cues present
_DOMAIN_CUE_WEAK_BOOST   = 0.06   # exactly one domain cue present
_DOMAIN_CUE_MISMATCH_PENALTY = 0.04  # entry's domain has 0 cues but
                                      # another candidate's domain has >= 2


@dataclass
class BoxXConsultation:
    """Inspectable result of a Box X consultation call."""
    consulted:       bool                       = False
    reason:          str                        = ""
    hits:            List[Dict[str, Any]]       = field(default_factory=list)
    notes:           List[str]                  = field(default_factory=list)

    def has_hit(self) -> bool:
        return bool(self.hits)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "consulted":  self.consulted,
            "reason":     self.reason,
            "hit_count":  len(self.hits),
            "hits":       list(self.hits),
            "notes":      list(self.notes),
        }


def _matched_tokens(query: str) -> List[str]:
    if not query:
        return []
    low = query.lower()
    return [t for t in _CONSULT_TECHNICAL_TOKENS if t.lower() in low]


def should_consult_box_x(
    *,
    query: str,
    reference_intent: bool = False,
    technical_hint: bool = False,
) -> Tuple[bool, str, List[str]]:
    """Pure predicate: decide whether a Box X consultation is worthwhile.

    Returns ``(should, reason, matched_tokens)``. Never raises.
    """
    tokens = _matched_tokens(query)
    if tokens:
        return True, "technical_token_match", tokens
    if technical_hint:
        return True, "technical_hint_flag", []
    if reference_intent:
        return True, "reference_intent_flag", []
    return False, "nontechnical_and_no_reference_intent", []


def consult_box_x(
    *,
    query: str,
    store: Any,
    top_k: int = 3,
    reference_intent: bool = False,
    technical_hint: bool = False,
    min_quality: float = _BOX_X_CONSULT_MIN_QUALITY,
) -> BoxXConsultation:
    """Consult Box X for curated references relevant to ``query``.

    Args:
      query          : the user query string.
      store          : a ``BoxXStore`` instance (or anything with
                       ``search_terms``, ``find_by_canonical_term`` and
                       ``list_entries_for_ui``).
      top_k          : maximum number of hits to return.
      reference_intent: caller hint that the query is reference-seeking.
      technical_hint : caller hint that the query is technical/definitional.
      min_quality    : drop hits whose quality_score is below this.

    Returns a ``BoxXConsultation`` with inspectable notes.
    """
    notes: List[str] = []
    # Gate first. When the store is missing or empty we still return a
    # clean "no hit" result with a reason, not an exception.
    if store is None:
        notes.append(NOTE_BOX_X_MISS)
        return BoxXConsultation(
            consulted=False, reason="no_store", notes=notes,
        )
    try:
        is_empty = getattr(store, "is_empty", None)
        if callable(is_empty) and store.is_empty():
            notes.append(NOTE_BOX_X_MISS)
            return BoxXConsultation(
                consulted=True, reason="store_empty",
                notes=notes + [NOTE_BOX_X_CONSULTED],
            )
    except Exception:
        pass

    should, reason, tokens = should_consult_box_x(
        query=query,
        reference_intent=reference_intent,
        technical_hint=technical_hint,
    )
    if not should:
        notes.append(NOTE_BOX_X_SKIPPED_NONTECHNICAL)
        return BoxXConsultation(
            consulted=False, reason=reason, notes=notes,
        )

    notes.append(NOTE_BOX_X_CONSULTED)

    # Strategy:
    #   1. Try each matched technical token first (precise path).
    #   2. Fall back to matching by every canonical term of every
    #      loaded entry that overlaps the query casefold substring.
    seen: set[str] = set()
    hits: List[Dict[str, Any]] = []

    def _take(entry) -> None:
        if entry.entry_id in seen:
            return
        qscore = float(getattr(entry, "quality_score", 0.0) or 0.0)
        if qscore < min_quality:
            return
        seen.add(entry.entry_id)
        hits.append({
            "entry_id":        entry.entry_id,
            "title":           entry.title,
            "canonical_terms": list(entry.canonical_terms),
            "domain":          entry.domain,
            "source_family":   entry.source_family,
            "source_uri":      entry.source_uri,
            "quality_score":   qscore,
            "staleness_state": entry.staleness_state,
        })

    if tokens:
        try:
            for e in store.search_terms(tokens, top_k=max(top_k * 2, top_k)):
                _take(e)
                if len(hits) >= top_k:
                    break
        except Exception as exc:   # noqa: BLE001
            logger.debug("[BoxX] search_terms failed: %s", exc)

    if len(hits) < top_k:
        # Fallback: scan entries and check if any canonical term is a
        # substring of the query. Bounded by entry count; Box X is a
        # curated layer, not a giant index.
        try:
            low_query = query.lower()
            for e in store.snapshot():
                if len(hits) >= top_k:
                    break
                for term in list(e.canonical_terms) + [e.title]:
                    if term and term.lower() in low_query:
                        _take(e)
                        break
        except Exception as exc:   # noqa: BLE001
            logger.debug("[BoxX] snapshot scan failed: %s", exc)

    if hits:
        # Inspectability — record how many candidates were considered
        # before ranking, so a downstream reader can distinguish
        # "1 candidate, no tie to break" from "4 candidates, one was
        # chosen via disambiguation".
        notes.append(f"box_x_candidate_count={len(hits)}")

        # Stage 8 — domain-cue disambiguation boost. When the candidate
        # set contains multiple entries (common for ambiguous surface
        # forms like "kernel" or "buffer"), apply a bounded score
        # adjustment based on nearby domain cues in the query. Never
        # displaces the quality floor; only reorders.
        if len(hits) > 1:
            cue_notes, hits = _apply_domain_disambiguation(
                query=query, hits=hits,
            )
            if cue_notes:
                notes.extend(cue_notes)

        # Drop any below quality floor already filtered; enforce sort.
        hits.sort(
            key=lambda h: -(
                float(h.get("quality_score") or 0.0)
                + float(h.get("_domain_cue_boost") or 0.0)
            )
        )
        hits = hits[:top_k]
        notes.append(NOTE_BOX_X_HIT)
        notes.append(NOTE_BOX_X_REFERENCE_USED)
        # If the top hit's quality is under a tighter sanity bar,
        # emit an extra skipped-low-confidence note so inspection can
        # distinguish "hit" vs "hit but iffy".
        top_q = float(hits[0].get("quality_score") or 0.0)
        if top_q < (min_quality + 0.10):
            notes.append(NOTE_BOX_X_SKIPPED_LOW_CONFIDENCE)
        return BoxXConsultation(
            consulted=True, reason="hit", hits=hits, notes=notes,
        )

    notes.append(NOTE_BOX_X_MISS)
    return BoxXConsultation(
        consulted=True, reason="no_hit_for_tokens", hits=[], notes=notes,
    )


def _count_domain_cues(domain: str, low_query: str) -> int:
    """Count how many tokens from the domain's cue list appear in the
    lowercased query. Returns 0 for unknown domains.
    """
    cues = _DOMAIN_DISAMBIG_CUES.get(domain) or []
    return sum(1 for c in cues if c and c.lower() in low_query)


def _apply_domain_disambiguation(
    *, query: str, hits: List[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Bounded domain-cue boost. Mutates each hit dict to attach a
    ``_domain_cue_boost`` value used by the subsequent sort. Never
    crosses the quality_floor boundary. Pure deterministic function.

    Returns (notes, hits). Notes include compact inspectable tokens
    such as ``box_x_domain_disambiguation_applied`` and
    ``box_x_domain_cue_<domain>_N`` for the top-boosted entry.
    """
    low_q = (query or "").lower()
    # Count cues per candidate domain.
    per_hit_counts: List[int] = []
    for h in hits:
        dom = str(h.get("domain") or "")
        per_hit_counts.append(_count_domain_cues(dom, low_q))
    max_cues = max(per_hit_counts) if per_hit_counts else 0
    if max_cues == 0:
        # No domain cues present; return unchanged.
        return [], hits

    for h, cues in zip(hits, per_hit_counts):
        if cues >= 2:
            h["_domain_cue_boost"] = _DOMAIN_CUE_STRONG_BOOST
        elif cues == 1:
            h["_domain_cue_boost"] = _DOMAIN_CUE_WEAK_BOOST
        else:
            # This entry's domain has no cues, but another candidate's
            # does — apply a small penalty so the cue-backed entry wins
            # on equal-quality ties.
            if max_cues >= 2:
                h["_domain_cue_boost"] = -_DOMAIN_CUE_MISMATCH_PENALTY
            else:
                h["_domain_cue_boost"] = 0.0

    # Provisional winner note for inspectability.
    boosted = max(
        ((i, h) for i, h in enumerate(hits)),
        key=lambda ih: ih[1].get("_domain_cue_boost") or 0.0,
    )
    win_idx, win_h = boosted
    win_cues = per_hit_counts[win_idx]
    win_dom = str(win_h.get("domain") or "unknown")
    notes = [
        "box_x_domain_disambiguation_applied",
        f"box_x_domain_cue_{win_dom.replace(' ', '_')}={win_cues}",
    ]
    return notes, hits
