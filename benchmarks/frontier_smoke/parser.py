"""Phase 2 — parsers and SimpleQA scorer for the frontier smoke.

Layers per the spec §4. All three parsing entry points return a
ParseResult(parsed, layer, parse_failure).

Routing precedence (§4.4) is enforced by `apply_routing_precedence()`
which the runner calls BEFORE invoking the parser, so the parser itself
never sees `routing_decision != "answer"` cases.
"""
from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


# ─── shared ──────────────────────────────────────────────────────────────

NEGATION_PATTERNS = (
    "not", "isn't", "wasn't", "incorrect", "wrong", "exclude",
    "n't ", "never",
)

ABSTAIN_PATTERNS = (
    "i don't know", "i do not know", "idk",
    "i'm not sure", "i am not sure",
    "unable to determine", "cannot verify", "can't verify",
    "insufficient information", "not enough information",
    "no way to know", "no reliable way",
)


@dataclass(frozen=True)
class ParseResult:
    parsed: Optional[str]
    layer: str
    parse_failure: bool


# ─── routing precedence (§4.4) ───────────────────────────────────────────

def apply_routing_precedence(routing_decision: Optional[str]) -> Optional[ParseResult]:
    """If routing != answer (and is set), return a routing_override result.

    Returns None when routing is None or 'answer' — meaning the parser
    should proceed normally.
    """
    if routing_decision is None or routing_decision == "answer":
        return None
    return ParseResult(parsed=None, layer="routing_override", parse_failure=False)


# ─── letter parser (MMLU-Pro / GPQA) ─────────────────────────────────────

def _is_letter(token: str, valid: str) -> bool:
    return len(token) == 1 and token in valid


def _has_negation_nearby(text: str, idx: int, window: int = 30) -> bool:
    start = max(0, idx - window)
    pre = text[start:idx].lower()
    return any(p in pre for p in NEGATION_PATTERNS)


def parse_letter(response: str, valid_letters: str = "ABCDEFGHIJ") -> ParseResult:
    if response is None:
        return ParseResult(None, "parse_failure", True)
    raw = response.strip()
    valid_set = set(valid_letters)

    # Layer 1: exact ("B", "B.", "B)" — punctuation tolerant)
    stripped = raw.rstrip(".)").strip()
    if len(stripped) == 1 and stripped in valid_set:
        return ParseResult(stripped, "exact", False)

    # Layer 2: bold markdown "**B**"
    m = re.search(r"\*\*\s*([" + re.escape(valid_letters) + r"])\s*\*\*", raw)
    if m:
        return ParseResult(m.group(1), "bold_markdown", False)

    # Layer 3: tagged forms
    tag_patterns = [
        r"\banswer(?:\s+is)?\s*[:\-]?\s*\(?([" + re.escape(valid_letters) + r"])\)?\b",
        r"\bthe\s+answer\s+is\s+\(?([" + re.escape(valid_letters) + r"])\)?\b",
        r"\bcorrect\s+answer\s+is\s*\(?([" + re.escape(valid_letters) + r"])\)?\b",
        r"\b(?:i\s+choose|i\s+pick|i\s+select|i\s+go\s+with)\s+\(?([" + re.escape(valid_letters) + r"])\)?\b",
        r"\boption\s+\(?([" + re.escape(valid_letters) + r"])\)?\b",
        r"\bchoice\s+\(?([" + re.escape(valid_letters) + r"])\)?\b",
    ]
    for p in tag_patterns:
        m = re.search(p, raw, flags=re.IGNORECASE)
        if m:
            cand = m.group(1).upper()
            if cand in valid_set:
                return ParseResult(cand, "tagged", False)

    # Layer 4: terminal parenthesized "(B)." or "(B)"
    m = re.search(r"\(([" + re.escape(valid_letters) + r"])\)\s*\.?\s*$", raw)
    if m:
        return ParseResult(m.group(1), "parenthesized_terminal", False)

    # Layer 5: \boxed{B}
    m = re.search(r"\\boxed\{\s*([" + re.escape(valid_letters) + r"])\s*\}", raw)
    if m:
        return ParseResult(m.group(1), "boxed", False)

    # Layer 6: last standalone letter in first 300 chars + negation guard
    head = raw[:300]
    last: Optional[Tuple[str, int]] = None
    for m in re.finditer(r"(?<![A-Za-z])([" + re.escape(valid_letters) + r"])(?![A-Za-z])", head):
        last = (m.group(1), m.start())
    if last is not None and not _has_negation_nearby(head, last[1]):
        return ParseResult(last[0], "last_standalone", False)

    return ParseResult(None, "parse_failure", True)


# ─── number parser (TruthfulQA MC1) ──────────────────────────────────────

def parse_number(response: str, max_choices: int) -> ParseResult:
    if response is None:
        return ParseResult(None, "parse_failure", True)
    raw = response.strip()
    valid = set(str(i) for i in range(1, max_choices + 1))

    # Layer 1: exact
    stripped = raw.rstrip(".)").strip()
    if stripped in valid:
        return ParseResult(stripped, "exact", False)

    # Layer 2: bold "**3**"
    m = re.search(r"\*\*\s*(\d+)\s*\*\*", raw)
    if m and m.group(1) in valid:
        return ParseResult(m.group(1), "bold_markdown", False)

    # Layer 3: tagged
    tag_patterns = [
        r"\banswer(?:\s+is)?\s*[:\-]?\s*(\d+)\b",
        r"\bthe\s+answer\s+is\s+(\d+)\b",
        r"\boption\s+(\d+)\b",
        r"\bchoice\s+(\d+)\b",
        r"\b(?:i\s+choose|i\s+pick|i\s+select)\s+(\d+)\b",
    ]
    for p in tag_patterns:
        m = re.search(p, raw, flags=re.IGNORECASE)
        if m and m.group(1) in valid:
            return ParseResult(m.group(1), "tagged", False)

    # Layer 4: first in-range digit within head 200 chars
    head = raw[:200]
    for m in re.finditer(r"(?<!\d)(\d+)(?!\d)", head):
        if m.group(1) in valid:
            return ParseResult(m.group(1), "first_in_range", False)

    return ParseResult(None, "parse_failure", True)


# ─── SimpleQA scorer (§4.3) ──────────────────────────────────────────────

@dataclass(frozen=True)
class SimpleQAResult:
    verdict: str           # correct | incorrect | abstain | routing_override | judge_review
    scoring_layer: str
    abstain_detected: bool
    needs_judge_review: bool
    parsed: Optional[str]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    # leading articles
    for a in ("the ", "a ", "an "):
        if text.startswith(a):
            text = text[len(a):]
    # punctuation → space (keep hyphen)
    out = []
    for ch in text:
        if ch == "-":
            out.append(ch)
        elif ch in string.punctuation:
            out.append(" ")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def score_simpleqa(
    response: str,
    gold: str,
    routing_decision: Optional[str] = None,
) -> SimpleQAResult:
    # Layer 0: routing override (highest precedence)
    if routing_decision is not None and routing_decision != "answer":
        return SimpleQAResult(
            verdict="routing_override",
            scoring_layer="routing_override",
            abstain_detected=False,
            needs_judge_review=False,
            parsed=None,
        )

    # Layer 1: empty
    if response is None or not response.strip():
        return SimpleQAResult("incorrect", "empty_response",
                              False, False, None)

    text = response.strip()
    lower = text.lower()

    # Layer 3: abstain detection
    if any(p in lower for p in ABSTAIN_PATTERNS):
        return SimpleQAResult("abstain", "abstain_detected",
                              True, False, None)

    # Layer 4: normalized exact match
    n_resp = _normalize(text)
    n_gold = _normalize(gold)
    if n_gold and n_resp == n_gold:
        return SimpleQAResult("correct", "exact_normalized",
                              False, False, n_resp)

    # Layer 5: word-boundary substring + negation guard
    if n_gold:
        pat = r"\b" + re.escape(n_gold) + r"\b"
        m = re.search(pat, n_resp)
        if m and not _has_negation_nearby(n_resp, m.start()):
            # Layer 6 judge_review triggers
            if len(n_gold) <= 3 and m.start() >= 50:
                return SimpleQAResult("judge_review",
                                      "short_gold_late_match",
                                      False, True, n_gold)
            return SimpleQAResult("correct", "substring_word_boundary",
                                  False, False, n_gold)

    # Layer 6 (other branch): verbose response with single-token gold,
    # no match at L5
    if len(text) > 100 and " " not in gold.strip():
        return SimpleQAResult("judge_review",
                              "verbose_with_single_token_gold",
                              False, True, None)

    # Layer 7: incorrect
    return SimpleQAResult("incorrect", "no_match", False, False, None)
