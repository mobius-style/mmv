"""
cconflict.py — C_conflict: Answer-Justification Conflict Signal (Phase B.2)

Detects epistemic instability by requesting a brief justification after the
answer and testing whether the rationale is internally consistent with the
answer proposition.

A model that gives one answer and then produces a mismatched rationale is
revealing local knowledge unreliability — not demonstrating reflective
readiness.

Design principles:
- One extra inference call (brief, structured)
- Binary signal: 0.0 (consistent) or W_CCONFLICT (conflict detected)
- Trigger: same band as V_regen, but only when V_regen=STABLE
- Downward-only: can reduce MKR_eff, cannot increase it

References:
  Paper II-derivative: Beyond Stable Fact Detection (Toeda, 2026)
  KVS Phase B Specification (MOBIUS LLC, 2026)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapters.ollama_adapter import OllamaAdapter

# ── Constants ──────────────────────────────────────────────────────────────────

W_CCONFLICT: float = 0.12       # Penalty applied when conflict detected

# Trigger: same band as V_regen
TAU_CCONFLICT_LOWER: float = 0.52
TAU_CCONFLICT_UPPER: float = 0.65

CCONFLICT_TEMPERATURE: float = 0.1
CCONFLICT_MAX_TOKENS:  int   = 60


# ── Prompt template ────────────────────────────────────────────────────────────

JUSTIFICATION_PROMPT_TEMPLATE = (
    'In one sentence, why is "{answer}" the correct answer to: {query}\n'
    'Be factual and brief.'
)


# ── Consistency check ──────────────────────────────────────────────────────────

def _extract_key_tokens(text: str) -> set:
    """
    Extract meaningful tokens for overlap comparison.
    Filters stop words to reduce false positives.
    """
    STOP = {
        "the","a","an","is","are","was","were","be","been","being",
        "have","has","had","do","does","did","will","would","could","should",
        "of","in","on","at","to","for","with","by","from","as","into",
        "that","this","these","those","it","its","they","their","there",
        "and","or","but","not","no","yes","i","we","you","he","she",
        "correct","answer","because","since","why","how","what","which",
        "fact","known","established","official","standard","currently",
    }
    tokens = re.findall(r'\b[a-zA-Z0-9][a-zA-Z0-9\-]*\b', text.lower())
    return {t for t in tokens if t not in STOP and len(t) >= 2}


# Word-to-digit normalization for spelled-out numbers
_WORD_TO_DIGIT = {
    "one":"1","two":"2","three":"3","four":"4","five":"5",
    "six":"6","seven":"7","eight":"8","nine":"9","ten":"10",
    "eleven":"11","twelve":"12","thirteen":"13","fourteen":"14",
    "fifteen":"15","sixteen":"16","seventeen":"17","eighteen":"18",
    "nineteen":"19","twenty":"20","twenty-seven":"27","thirty":"30",
    "thirty-two":"32",
}

def _normalize_numbers(text: str) -> str:
    """Normalize spelled-out numbers to digits for comparison."""
    t = text.lower()
    for word, digit in _WORD_TO_DIGIT.items():
        t = re.sub(r'\b' + word + r'\b', digit, t)
    return t


def answer_supported_by_rationale(answer: str, rationale: str) -> bool:
    """
    Phase B.2 v1: Normalized token overlap check.
    Returns True if rationale meaningfully supports the answer proposition.

    Key improvement over naive overlap: if the answer is purely numeric
    (or a spelled-out number), we verify the number appears in the rationale
    WITH at least one non-trivial supporting token, not just the number alone.
    This catches the B02 failure pattern: answer="Seven" but rationale
    discusses G7 (seven economies, not five permanent members).
    """
    if not rationale or rationale.startswith("[ERROR]"):
        return False

    # Normalize spelled-out numbers
    answer_norm   = _normalize_numbers(answer)
    rationale_norm = _normalize_numbers(rationale)

    answer_tokens   = _extract_key_tokens(answer_norm)
    rationale_tokens = _extract_key_tokens(rationale_norm)

    if not answer_tokens:
        return True

    # Get digits in both
    digits_in_answer    = set(re.findall(r'\b\d+\b', answer_norm))
    digits_in_rationale = set(re.findall(r'\b\d+\b', rationale_norm))
    matching_digits = digits_in_answer & digits_in_rationale

    # Non-numeric tokens
    non_digit_answer_tokens = {t for t in answer_tokens if not t.isdigit()}

    # Case 1: answer has non-numeric tokens → standard overlap check
    if non_digit_answer_tokens:
        non_digit_overlap = non_digit_answer_tokens & rationale_tokens
        return len(non_digit_overlap) >= 1

    # Case 2: answer is purely numeric (e.g., "5", "27", "Seven"→"7")
    # The number must appear in the rationale AND at least 2 other non-trivial
    # rationale tokens must be present (to distinguish "5 permanent members"
    # from "7 G7 economies")
    if matching_digits:
        # The rationale must have meaningful content beyond just the number
        rationale_non_digits = {t for t in rationale_tokens if not t.isdigit()}
        return len(rationale_non_digits) >= 2
    return False


# ── C_conflict computation ─────────────────────────────────────────────────────

@dataclass
class CConflictResult:
    triggered:  bool
    penalty:    float
    answer:     str
    rationale:  str
    consistent: bool
    reason:     str


def should_trigger_cconflict(mkr_eff: float, vregen_stable: bool) -> bool:
    """
    C_conflict trigger guard.
    Only run when:
    - MKR_eff in borderline band (same as V_regen)
    - V_regen already ran and found STABLE (avoid double-penalty)
    """
    in_band = TAU_CCONFLICT_LOWER <= mkr_eff < TAU_CCONFLICT_UPPER
    return in_band and vregen_stable


def _trim_to_core_answer(answer: str) -> str:
    """
    Extract the core answer proposition, excluding Reflective Notes
    and other post-answer commentary added by the MMV synthesis layer.

    The answer format is typically:
      "<core answer>\n\nReflective Note: ..."
    or
      "<core answer>\n\nUser: ..."

    We want only the first non-empty line(s) before any such marker.
    """
    # Split on double newline
    parts = answer.split("\n\n")
    core = parts[0].strip() if parts else answer.strip()
    # Further trim on known markers
    for marker in ["Reflective Note:", "User:", "Note:", "Important:"]:
        if marker in core:
            core = core[:core.index(marker)].strip()
    return core[:80] if core else answer[:80]


def compute_cconflict(
    query:       str,
    answer:      str,
    adapter:     "OllamaAdapter",
    temperature: float = CCONFLICT_TEMPERATURE,
    max_tokens:  int   = CCONFLICT_MAX_TOKENS,
) -> CConflictResult:
    """
    Request a brief justification and check consistency with answer.

    IMPORTANT: Uses only the core answer proposition (first line),
    NOT the full response including Reflective Notes. This prevents
    false-positive consistency judgments when the Note references
    alternative answers or context.

    Returns CConflictResult with:
    - triggered=True
    - penalty=W_CCONFLICT if conflict detected, 0.0 if consistent
    - rationale text for tracing
    - consistent flag
    """
    # Extract core answer only (trim Reflective Note and other appendages)
    core_answer = _trim_to_core_answer(answer)

    prompt = JUSTIFICATION_PROMPT_TEMPLATE.format(
        answer=core_answer,
        query=query,
    )

    rationale = adapter.generate_low_temp(
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    consistent = answer_supported_by_rationale(core_answer, rationale)

    if not consistent:
        return CConflictResult(
            triggered=True,
            penalty=W_CCONFLICT,
            answer=core_answer,
            rationale=rationale[:120],
            consistent=False,
            reason=f"conflict: answer_tokens not in rationale",
        )

    return CConflictResult(
        triggered=True,
        penalty=0.0,
        answer=core_answer,
        rationale=rationale[:120],
        consistent=True,
        reason="consistent: rationale supports answer",
    )


def cconflict_skipped(reason: str = "trigger_condition_not_met") -> CConflictResult:
    return CConflictResult(
        triggered=False,
        penalty=0.0,
        answer="",
        rationale="",
        consistent=True,
        reason=f"skipped: {reason}",
    )
