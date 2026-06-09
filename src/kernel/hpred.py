"""
hpred.py — H_pred: Entropy-Like Prediction Instability Signal (Phase B.3)

Computes a normalized entropy proxy from token-level log-probabilities
returned by the Ollama /api/chat endpoint (logprobs=true, top_k=5).

When logprobs are unavailable (API limitation or older Ollama version),
falls back gracefully to a no-op (penalty=0.0, triggered=False).

Design principles:
- Uses only the first max_answer_tokens of the response (answer span)
- Normalized to [0,1] by dividing per-position entropy by log(k)
- Averaged across answer positions to get a single H_pred score
- Trigger: same MKR_eff band as V_regen and C_conflict [0.52, 0.65]
- Downward-only: can only decrease MKR_eff

References:
  Paper II-derivative: Beyond Stable Fact Detection (Toeda, 2026)
  KVS Phase B Specification (MOBIUS LLC, 2026)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..adapters.ollama_adapter import OllamaAdapter

# ── Constants ──────────────────────────────────────────────────────────────────

W_HPRED: float = 0.10           # Penalty weight
TAU_HPRED_LOWER: float = 0.52   # Same trigger band as V_regen / C_conflict
TAU_HPRED_UPPER: float = 0.65

# Entropy threshold above which penalty is applied
HPRED_HIGH_ENTROPY_THRESHOLD: float = 0.80  # 3/4 samples same → diversity=0.25→h=0.375 (low); 2/4 diff → h=0.75 (borderline); all diff → h=1.0 (HIGH)

# How many answer tokens to use for entropy calculation
MAX_ANSWER_TOKENS: int = 8

# Number of top logprobs to request from Ollama
TOP_K_LOGPROBS: int = 5

HPRED_TEMPERATURE: float = 0.0   # Deterministic for logprob measurement
HPRED_MAX_TOKENS:  int   = 12


# ── Entropy computation ────────────────────────────────────────────────────────

def _position_entropy(top_logprobs: list[dict]) -> float:
    """
    Compute normalized entropy for one token position.
    top_logprobs: [{"token": str, "logprob": float}, ...]
    Returns H_norm in [0, 1].
    """
    if not top_logprobs:
        return 0.0

    logprobs = [item.get("logprob", -10.0) for item in top_logprobs]
    probs = [math.exp(lp) for lp in logprobs]

    total = sum(probs)
    if total <= 0:
        return 0.0

    probs = [p / total for p in probs]
    k = len(probs)
    if k <= 1:
        return 0.0

    h_raw = -sum(p * math.log(p + 1e-12) for p in probs if p > 0)
    h_norm = h_raw / math.log(k)   # normalize by log(k) → [0, 1]
    return max(0.0, min(1.0, h_norm))


def compute_entropy_from_logprobs(
    logprobs_content: list[dict],
    max_tokens: int = MAX_ANSWER_TOKENS,
) -> float:
    """
    Average normalized entropy across answer token positions.

    logprobs_content: Ollama /api/chat response logprobs.content list
      Each item: {"token": str, "logprob": float, "top_logprobs": [...]}
    """
    entropies = []
    for item in logprobs_content[:max_tokens]:
        top = item.get("top_logprobs", [])
        if not top:
            # Fallback: use single token logprob as a point estimate
            lp = item.get("logprob", 0.0)
            # High negative logprob → uncertain token
            single_entropy = min(1.0, max(0.0, -lp / 10.0))
            entropies.append(single_entropy)
        else:
            entropies.append(_position_entropy(top))

    return sum(entropies) / len(entropies) if entropies else 0.0


# ── Ollama logprob call ────────────────────────────────────────────────────────

# Sampling temperatures for multi-sample entropy estimation
SAMPLE_TEMPERATURES: list[float] = [0.0, 0.05, 0.10, 0.20]

def _request_logprobs(
    prompt: str,
    adapter: "OllamaAdapter",
    max_tokens: int = HPRED_MAX_TOKENS,
    top_k: int = TOP_K_LOGPROBS,
) -> Optional[list[dict]]:
    """
    Call Ollama /api/chat with logprobs=true.

    NOTE: Current Ollama versions return only top-1 logprob per token
    (no top_logprobs array). This function attempts the call and returns
    the logprobs list if available with top_logprobs, otherwise None.

    If None is returned, compute_hpred falls back to multi-temperature
    sampling as an entropy proxy.
    """
    import requests

    endpoint = getattr(adapter, 'endpoint', 'http://localhost:11434')
    model    = getattr(adapter, 'model_name', 'phi4-mini:latest')
    url      = f"{endpoint.rstrip('/')}/api/chat"

    payload = {
        "model":    model,
        "messages": [{"role": "user", "content": prompt}],
        "stream":   False,
        "logprobs": True,
        "top_k":    top_k,
        "options":  {
            "num_predict": max_tokens,
            "temperature": HPRED_TEMPERATURE,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=40)
        resp.raise_for_status()
        data = resp.json()

        # Try dict format first (newer Ollama)
        lp = data.get("logprobs")
        if lp and isinstance(lp, dict):
            content = lp.get("content")
            if content and isinstance(content, list):
                # Check if top_logprobs are present
                if any("top_logprobs" in item for item in content):
                    return content

        # List format (older Ollama) — top-1 only, not useful for entropy
        return None

    except Exception:
        return None


def _multi_sample_entropy(
    prompt: str,
    adapter: "OllamaAdapter",
    temperatures: list[float] = SAMPLE_TEMPERATURES,
    max_tokens: int = 8,
) -> float:
    """
    Estimate prediction entropy via token diversity across multiple
    low-temperature samples.

    Strategy: run the same prompt at 4 temperatures (0.0, 0.05, 0.10, 0.20).
    Extract the first meaningful token from each response.
    Token diversity (unique tokens / total samples) approximates entropy.

    This is a cheaper proxy than true logprob entropy but requires
    no special API support.
    """
    import re
    tokens = []
    prompt_short = f"Answer with one word or number only: {prompt}"

    for temp in temperatures:
        try:
            resp = adapter.generate_low_temp(
                prompt=prompt_short,
                temperature=temp,
                max_tokens=max_tokens,
            )
            if resp and not resp.startswith("[ERROR]"):
                # Extract first token (first word/number)
                first = re.split(r'[\s\n,.]', resp.strip())[0].lower()
                if first:
                    tokens.append(first)
        except Exception:
            pass

    if len(tokens) < 2:
        return 0.0  # Cannot estimate

    unique = len(set(tokens))
    total  = len(tokens)
    # Diversity ratio → entropy proxy [0, 1]
    # diversity=1/4=0.25 (all same) → h≈0.0
    # diversity=4/4=1.0  (all diff) → h≈1.0
    diversity = unique / total
    # Scale: below 0.5 is low entropy, above 0.75 is high entropy
    # Normalize to [0, 1] smoothly
    h_proxy = min(1.0, diversity * 1.5)
    return round(h_proxy, 4)


# ── H_pred signal ──────────────────────────────────────────────────────────────

@dataclass
class HPredResult:
    triggered:     bool
    available:     bool      # False if logprobs not supported by this Ollama
    h_score:       float     # Average normalized entropy [0, 1]
    penalty:       float     # 0.0 or W_HPRED
    reason:        str


def should_trigger_hpred(mkr_eff: float) -> bool:
    return TAU_HPRED_LOWER <= mkr_eff < TAU_HPRED_UPPER


def compute_hpred(
    query:     str,
    adapter:   "OllamaAdapter",
    max_tokens: int = HPRED_MAX_TOKENS,
    top_k:     int  = TOP_K_LOGPROBS,
) -> HPredResult:
    """
    Compute H_pred entropy signal.

    Strategy (in order of preference):
    1. Ollama logprobs with top_logprobs → true entropy calculation
    2. Multi-temperature sampling → token diversity as entropy proxy
    3. Graceful degradation → penalty=0.0, triggered=False
    """
    prompt = f"Answer in one word or number only: {query}"

    # Try true logprob entropy first
    logprobs_content = _request_logprobs(
        prompt=prompt,
        adapter=adapter,
        max_tokens=max_tokens,
        top_k=top_k,
    )

    if logprobs_content is not None:
        # True entropy from top_logprobs
        h_score = compute_entropy_from_logprobs(logprobs_content, max_tokens)
        method = "logprobs"
    else:
        # Fallback: multi-temperature sampling entropy proxy
        h_score = _multi_sample_entropy(
            prompt=query,
            adapter=adapter,
            temperatures=SAMPLE_TEMPERATURES,
            max_tokens=max_tokens,
        )
        method = "multi_sample"

    high_entropy = h_score >= HPRED_HIGH_ENTROPY_THRESHOLD

    if high_entropy:
        return HPredResult(
            triggered=True,
            available=True,
            h_score=h_score,
            penalty=W_HPRED,
            reason=f"high_entropy [{method}]: H={h_score:.3f} >= {HPRED_HIGH_ENTROPY_THRESHOLD}",
        )

    return HPredResult(
        triggered=True,
        available=True,
        h_score=h_score,
        penalty=0.0,
        reason=f"low_entropy [{method}]: H={h_score:.3f} < {HPRED_HIGH_ENTROPY_THRESHOLD}",
    )


def hpred_skipped(reason: str = "trigger_condition_not_met") -> HPredResult:
    return HPredResult(
        triggered=False,
        available=True,
        h_score=0.0,
        penalty=0.0,
        reason=f"skipped: {reason}",
    )
