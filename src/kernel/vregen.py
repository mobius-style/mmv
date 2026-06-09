"""
vregen.py — V_regen: Regeneration Variance Signal for KVS Phase B.1

Detects local model instability by running 2 additional low-temperature
restatements and comparing the core proposition to the original answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapters.ollama_adapter import OllamaAdapter

# ── Constants ──────────────────────────────────────────────────────────────────
W_VREGEN: float = 0.15
TAU_VREGEN_LOWER: float = 0.52   # = tau_M
TAU_VREGEN_UPPER: float = 0.65   # above this → skip

VREGEN_TEMPERATURE: float = 0.05
VREGEN_MAX_TOKENS:  int   = 50
VREGEN_N_RUNS:      int   = 2


# ── Core proposition extraction ────────────────────────────────────────────────

_NUMBER_PATTERN = re.compile(
    r'\b(\d{1,4}(?:[,.]\d{3})*(?:\.\d+)?)\b'
)
_WORD_NUMBER_PATTERN = re.compile(
    r'\b(one|two|three|four|five|six|seven|eight|nine|ten'
    r'|eleven|twelve|thirteen|fourteen|fifteen|sixteen'
    r'|seventeen|eighteen|nineteen|twenty)\b',
    re.IGNORECASE,
)
_WORD_TO_NUM = {
    "one":"1","two":"2","three":"3","four":"4","five":"5",
    "six":"6","seven":"7","eight":"8","nine":"9","ten":"10",
    "eleven":"11","twelve":"12","thirteen":"13","fourteen":"14",
    "fifteen":"15","sixteen":"16","seventeen":"17","eighteen":"18",
    "nineteen":"19","twenty":"20",
}
_PROPER_NOUN_PATTERN = re.compile(
    r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b'
)
_COUNTRY_CURRENCY_PATTERN = re.compile(
    r'\b(euro|dollar|pound|yen|franc|paris|london|berlin'
    r'|tokyo|ottawa|canberra|portuguese|english|french|german|japanese)\b',
    re.IGNORECASE,
)


def extract_core_proposition(text: str) -> str:
    """
    Extract the core factual claim from a short response.
    Priority: digit number → word number → title-case single noun → proper noun → geo/currency → fallback
    """
    text = text.strip()
    if not text or text.startswith("[ERROR]"):
        return "__error__"

    # 1a. Digit numbers
    m = _NUMBER_PATTERN.search(text)
    if m:
        return m.group(1).replace(",", "").lower()

    # 1b. Spelled-out numbers
    m = _WORD_NUMBER_PATTERN.search(text)
    if m:
        return _WORD_TO_NUM.get(m.group(1).lower(), m.group(1).lower())

    # 2. Known geo/currency terms (before proper noun to catch "Paris" etc.)
    m = _COUNTRY_CURRENCY_PATTERN.search(text)
    if m:
        return m.group(1).lower()

    # 3. Proper nouns (e.g., "Mark Carney", "António Guterres")
    m = _PROPER_NOUN_PATTERN.search(text)
    if m:
        return m.group(1).lower()

    # 4. Single title-case word
    m = re.search(r'(?:^|\s)([A-Z][a-z]{3,})(?:\s|$|[.,])', text)
    if m:
        return m.group(1).lower()

    # 5. Fallback
    return text[:20].lower().strip()


# ── V_regen computation ────────────────────────────────────────────────────────

@dataclass
class VRegenResult:
    triggered:    bool
    penalty:      float
    propositions: list
    stable:       bool
    reason:       str


def should_trigger_vregen(mkr_eff: float) -> bool:
    return TAU_VREGEN_LOWER <= mkr_eff < TAU_VREGEN_UPPER


def compute_vregen(
    query:           str,
    original_answer: str,
    adapter:         "OllamaAdapter",
    n_runs:          int   = VREGEN_N_RUNS,
    temperature:     float = VREGEN_TEMPERATURE,
    max_tokens:      int   = VREGEN_MAX_TOKENS,
) -> VRegenResult:
    original_prop = extract_core_proposition(original_answer)
    propositions  = [original_prop]

    for _ in range(n_runs):
        resp = adapter.generate_low_temp(
            prompt=query,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        propositions.append(extract_core_proposition(resp))

    has_error    = any(p == "__error__" for p in propositions)
    unique_props = set(p for p in propositions if p != "__error__")
    is_stable    = (not has_error) and (len(unique_props) == 1)

    if not is_stable:
        return VRegenResult(
            triggered=True, penalty=W_VREGEN,
            propositions=propositions, stable=False,
            reason=f"unstable: {propositions}",
        )
    return VRegenResult(
        triggered=True, penalty=0.0,
        propositions=propositions, stable=True,
        reason=f"stable: {original_prop}",
    )


def vregen_skipped(reason: str = "mkr_eff_outside_trigger_band") -> VRegenResult:
    return VRegenResult(
        triggered=False, penalty=0.0,
        propositions=[], stable=True,
        reason=f"skipped: {reason}",
    )
