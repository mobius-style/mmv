#!/usr/bin/env python3
"""
user_map.py — Phase E L3: UserMap + update rules

Trajectory-aware, user-fit layer on top of the existing Box M three-layer
architecture (L0 raw turns / L1 capsules / L2 active context). This L3 is NOT
for personality drift; it is only for distance calibration and fit inference.

Cold-start safety is a first-class concern: when there is insufficient history,
UserMap must make the system LESS presumptive, not more.

Non-goals (explicit):
    - Not a personality model
    - Not an ideology / emotional state tracker
    - Not a replacement for SessionState.user_profile (M-2)
    - Not persisted across sessions (stays in SessionState for the session)

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "MMV v2.1 Box M Enhancement Specification — Phase E"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ── Constants ───────────────────────────────────────────────────────────────

COLD_START_TURN_THRESHOLD    = 4
COLD_START_CONFIDENCE_FLOOR  = 0.45
HUMILITY_BAND_TURNS          = 3      # CS-1
DEEP_PREF_SUPPRESSION_TURNS  = 5      # CS-2

ABSTRACTION_CONCRETE   = 0.0
ABSTRACTION_STRUCTURAL = 1.0
ABSTRACTION_ECOSYSTEM  = 2.0

THEME_WEIGHT_RECENT   = 0.55
THEME_WEIGHT_REPEAT   = 0.30
THEME_WEIGHT_EXPLICIT = 0.15
THEME_THRESHOLD       = 0.58

# Spec §7.3 suggests 0.62 for full semantic overlap. In a token-set proxy
# (no stemming, no embeddings), plural/singular variants (monad vs monads)
# depress the ratio. We adopt 0.45 as the effective threshold — still well
# above random, but permits "substantive partial echo" as adoption.
ADOPTION_OVERLAP_THRESHOLD = 0.45

# Phase G.8 — multi-signal adoption scoring.
#
# The pure-lexical gate above is brittle in real dialogue: the assistant's
# response vocabulary diverges from the user's follow-up even when the
# user is still inside the same frame. G.8 adds a small weighted score
# that combines lexical overlap with three cooperative-continuation
# signals that are already tracked on UserMap:
#
#   - lexical overlap               (existing semantic_overlap)
#   - repeated explicit framing cue (user has signalled the same cue
#                                    previously and does so again, or is
#                                    continuing within the same framing
#                                    mode)
#   - theme continuity              (user turn shares at least one token
#                                    with existing active_themes)
#   - abstraction band agreement    (user turn's estimated abstraction
#                                    level matches the rolling baseline
#                                    within one band)
#
# Adoption fires when weighted_score >= ADOPTION_MULTI_SIGNAL_THRESHOLD,
# OR when the existing pure-lexical gate fires (so behavior is strictly
# monotone — only MORE adoptions than before, never fewer for a given
# lexical-match case). User corrections always block, as they did before.
ADOPTION_MULTI_SIGNAL_THRESHOLD = 0.4
# Partial lexical overlap is also lowered to improve realistic detection
# while still well above random (token overlap ratio of 0.25 still
# requires one-quarter of the shorter side to overlap).
ADOPTION_LEXICAL_FLOOR          = 0.25
ADOPTION_W_LEXICAL              = 0.4   # full lexical gate cross
ADOPTION_W_FRAMING_NEW          = 0.25  # fresh explicit cue in this turn
ADOPTION_W_FRAMING_REPEAT       = 0.15  # fresh cue that was also in history
ADOPTION_W_FRAMING_PERSISTENT   = 0.10  # prior cue still carried
ADOPTION_W_THEME_SHARED         = 0.2   # theme token in both turn and frame
ADOPTION_W_THEME_CONTINUATION   = 0.1   # theme touched in turn only
ADOPTION_W_ABSTRACTION          = 0.1   # abstraction band matches

COMFORT_ZONE_INIT = 0.35
COMFORT_ZONE_EMA_PREV = 0.8
COMFORT_ZONE_EMA_NEW  = 0.2

ABSTRACTION_EMA_PREV = 0.75
ABSTRACTION_EMA_NEW  = 0.25

# ── Explicit style cues (CS-4) ──────────────────────────────────────────────

EXPLICIT_CUE_PATTERNS = {
    # concise: also match 'concisely', 'concisely.', 'briefly', tl;dr, etc.
    "concise":     [r"\bconcise\w*\b", r"\bbriefly\b", r"\bshort(?:ly|er)?\b", r"\btl;?dr\b", r"in a nutshell", r"簡潔", r"短く", r"手短"],
    "detailed":    [r"\bdetailed?\w*\b", r"\bin[- ]depth\b", r"\bthorough\w*\b", r"\bcomprehensive\w*\b", r"詳しく", r"詳細", r"徹底"],
    "gentle":      [r"\bgentl\w*\b", r"\bsoft\w*\b", r"\bfriendly\b", r"\bkindly\b", r"優しく", r"やさしく"],
    "stepwise":    [r"\bstep[- ]by[- ]step\b", r"\bone step at a time\b", r"段階的", r"手順で"],
    "examples":    [r"\bexamples?\b", r"\be\.g\.", r"\bfor instance\b", r"concrete example", r"例で", r"具体例"],
    "direct":      [r"\bjust the answer\b", r"\bdirectly\b", r"\bno preamble\b", r"straight to the point", r"結論だけ", r"直接"],
    "theoretical": [r"\btheoretic\w*\b", r"\bin theory\b", r"\babstractly\b", r"理論で", r"抽象的"],
}

_cue_compiled = {
    name: [re.compile(p, re.IGNORECASE) for p in pats]
    for name, pats in EXPLICIT_CUE_PATTERNS.items()
}


def detect_explicit_cues(text: str) -> List[str]:
    """Return list of cue names present in text (CS-4 override signal)."""
    if not text:
        return []
    hits: List[str] = []
    for cue, regexes in _cue_compiled.items():
        if any(r.search(text) for r in regexes):
            hits.append(cue)
    return hits


# ── Light heuristics (no external models) ───────────────────────────────────


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[\w\u3040-\u30ff\u3400-\u9fff]+", (text or "").lower(), flags=re.UNICODE)


def _estimate_abstraction_label(turn_text: str) -> float:
    """
    Estimate abstraction level of a user turn.
    concrete (0.0) | structural (1.0) | ecosystem (2.0)
    Conservative heuristic; easy to audit.
    """
    if not turn_text:
        return ABSTRACTION_CONCRETE
    t = turn_text.lower()
    if re.search(r"\b(ecosystem|how does .{0,40} relate|framework|architecture of|relationship|interconnect)\b", t) \
            or "体系" in turn_text or "生態系" in turn_text:
        return ABSTRACTION_ECOSYSTEM
    if re.search(r"\b(how does|how do|explain|mechanism|process|why does|architecture|structure|concept)\b", t) \
            or "なぜ" in turn_text or "仕組み" in turn_text or "構造" in turn_text:
        return ABSTRACTION_STRUCTURAL
    return ABSTRACTION_CONCRETE


def semantic_overlap(a: str, b: str) -> float:
    """Simple set-based overlap ratio over salient tokens."""
    ta = {t for t in _tokenize(a) if len(t) >= 3}
    tb = {t for t in _tokenize(b) if len(t) >= 3}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


_USER_CORRECTION_PATTERNS = [
    r"\b(no,|that's not|that is not|actually|wrong|incorrect|not what i)\b",
    r"違う", r"そうじゃない", r"違います", r"いいえ", r"ちがう",
    r"\b(i meant|i mean|rather)\b",
    r"訂正", r"間違い",
]
_correction_re = re.compile("|".join(_USER_CORRECTION_PATTERNS), re.IGNORECASE)


def is_user_correction(text: str) -> bool:
    if not text:
        return False
    return bool(_correction_re.search(text))


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class UserMap:
    """L3 user-fit map. Deliberately minimal."""
    active_themes:        List[str]  = field(default_factory=list)
    theme_weights:        dict       = field(default_factory=dict)   # theme -> weighted score
    abstraction_baseline: float      = ABSTRACTION_CONCRETE
    framing_preferences:  List[str]  = field(default_factory=list)   # explicit cues observed
    observed_plateaus:    List[str]  = field(default_factory=list)
    adopted_frames:       List[str]  = field(default_factory=list)
    rejected_frames:      List[str]  = field(default_factory=list)
    comfort_zone:         float      = COMFORT_ZONE_INIT
    confidence:           float      = 0.0
    cold_start:           bool       = True

    # Lightweight counters used for confidence growth
    valid_turn_count: int = 0
    half_step_correction_count: int = 0

    def summary(self) -> dict:
        return {
            "cold_start":           self.cold_start,
            "confidence":           round(self.confidence, 3),
            "abstraction_baseline": round(self.abstraction_baseline, 3),
            "comfort_zone":         round(self.comfort_zone, 3),
            "active_themes":        list(self.active_themes),
            "framing_preferences":  list(self.framing_preferences),
            "adopted_frames":       list(self.adopted_frames),
            "rejected_frames":      list(self.rejected_frames),
            "valid_turn_count":     self.valid_turn_count,
        }


# ── Update rules ────────────────────────────────────────────────────────────


def update_cold_start(user_map: UserMap) -> None:
    """Refresh cold_start flag based on current map state."""
    user_map.cold_start = (
        user_map.valid_turn_count < COLD_START_TURN_THRESHOLD
        or user_map.confidence < COLD_START_CONFIDENCE_FLOOR
        or len(user_map.adopted_frames) == 0
        or len(user_map.active_themes) < 2
    )


def update_abstraction_baseline(user_map: UserMap, user_turn_text: str) -> None:
    """EMA update of abstraction baseline from a user turn."""
    a_t = _estimate_abstraction_label(user_turn_text)
    user_map.abstraction_baseline = (
        ABSTRACTION_EMA_PREV * user_map.abstraction_baseline
        + ABSTRACTION_EMA_NEW * a_t
    )


def update_comfort_zone(user_map: UserMap, turn_fit_score: float) -> None:
    """
    Update comfort_zone via EMA.
      0.2 = assistant too far (correction / ask-back)
      0.5 = neutral
      0.8 = half-step adopted
      1.0 = user asked for deeper framing themselves
    """
    x = max(0.0, min(1.0, float(turn_fit_score)))
    user_map.comfort_zone = max(
        0.0,
        min(1.0, COMFORT_ZONE_EMA_PREV * user_map.comfort_zone + COMFORT_ZONE_EMA_NEW * x),
    )


def update_themes(user_map: UserMap, user_turn_text: str, *, explicit: bool = False) -> None:
    """
    Lightweight theme tracker. A "theme candidate" is the set of salient
    tokens (len>=5) in the user turn; we aggregate weights across turns.
    """
    tokens = [t for t in _tokenize(user_turn_text) if len(t) >= 5]
    for tok in set(tokens):
        w_existing = user_map.theme_weights.get(tok, 0.0)
        w_recent   = 1.0  # always 1 for current turn
        w_repeat   = 1.0 if w_existing > 0 else 0.0
        w_explicit = 1.0 if explicit else 0.0
        delta = (
            THEME_WEIGHT_RECENT * w_recent
            + THEME_WEIGHT_REPEAT * w_repeat
            + THEME_WEIGHT_EXPLICIT * w_explicit
        )
        user_map.theme_weights[tok] = min(2.0, w_existing * 0.85 + delta)
        if user_map.theme_weights[tok] >= THEME_THRESHOLD and tok not in user_map.active_themes:
            user_map.active_themes.append(tok)


def compute_adoption_score(
    user_map: UserMap,
    assistant_frame: str,
    next_user_turn: str,
) -> tuple[float, List[str]]:
    """
    Phase G.8 — multi-signal weighted adoption score.

    Returns (score, signals_fired). Pure; does NOT mutate user_map.
    Signals considered:

      - lexical: token overlap between the user turn and the assistant
                 frame, counted at/above `ADOPTION_LEXICAL_FLOOR`. Full
                 `ADOPTION_OVERLAP_THRESHOLD` crossing gives a small
                 additional boost (to keep behavior monotone with the
                 pre-G.8 gate).
      - framing: the user turn emits at least one explicit style cue
                 (concise / detailed / structural / gentle / stepwise /
                 examples / direct / theoretical), OR an existing
                 framing_preference is still present after ≥3 turns.
      - theme:   the user turn shares at least one non-trivial token
                 with an already-active theme, signalling topic
                 continuation (not drift).
      - abstraction: user turn's estimated abstraction label sits
                     within one band of the rolling baseline.

    Correction rejection is handled by the caller; this function does
    not look at correction patterns.
    """
    signals: List[str] = []
    if not assistant_frame or not next_user_turn:
        return 0.0, signals

    score = 0.0

    # -- lexical --
    lex = semantic_overlap(next_user_turn, assistant_frame)
    if lex >= ADOPTION_OVERLAP_THRESHOLD:
        score += ADOPTION_W_LEXICAL
        signals.append(f"lex_full={lex:.2f}")
    elif lex >= ADOPTION_LEXICAL_FLOOR:
        # Scale linearly between floor and full threshold, capped at the
        # lexical weight.
        span = max(1e-6, ADOPTION_OVERLAP_THRESHOLD - ADOPTION_LEXICAL_FLOOR)
        frac = (lex - ADOPTION_LEXICAL_FLOOR) / span
        score += ADOPTION_W_LEXICAL * frac
        signals.append(f"lex_partial={lex:.2f}")

    # -- framing cue --
    cues_now = detect_explicit_cues(next_user_turn)
    prior_prefs = set(user_map.framing_preferences or [])
    if cues_now:
        score += ADOPTION_W_FRAMING_NEW
        signals.append(f"framing_cues={cues_now}")
        # Bonus when the fresh cue matches a previously-recorded one.
        if prior_prefs & set(cues_now):
            score += ADOPTION_W_FRAMING_REPEAT
            signals.append("framing_repeat")
    elif prior_prefs and user_map.valid_turn_count >= 3:
        score += ADOPTION_W_FRAMING_PERSISTENT
        signals.append("framing_persistent")

    # -- theme continuity --
    if user_map.active_themes:
        turn_tokens = {t for t in _tokenize(next_user_turn) if len(t) >= 5}
        frame_tokens = {t for t in _tokenize(assistant_frame) if len(t) >= 5}
        theme_set = set(user_map.active_themes)
        shared_via_frame = theme_set & turn_tokens & frame_tokens
        still_in_theme = theme_set & turn_tokens
        if shared_via_frame:
            score += ADOPTION_W_THEME_SHARED
            signals.append(f"theme_shared={sorted(shared_via_frame)[:3]}")
        elif still_in_theme:
            score += ADOPTION_W_THEME_CONTINUATION
            signals.append("theme_continuation")

    # -- abstraction band --
    abs_turn = _estimate_abstraction_label(next_user_turn)
    if abs(abs_turn - user_map.abstraction_baseline) <= 1.0:
        score += ADOPTION_W_ABSTRACTION
        signals.append("abstraction_band_match")

    return score, signals


def update_frame_adoption(
    user_map: UserMap,
    assistant_frame: str,
    next_user_turn: str,
) -> None:
    """
    Classify whether the user adopted, rejected, or ignored an assistant frame.

    Phase G.8: adoption now fires on either the classic pure-lexical
    gate OR the multi-signal score threshold. User corrections still
    dominate — corrections unconditionally mark the frame as rejected.
    """
    if not assistant_frame or not next_user_turn:
        return
    if is_user_correction(next_user_turn):
        if assistant_frame not in user_map.rejected_frames:
            user_map.rejected_frames.append(assistant_frame)
        return

    # Classic pure-lexical path — preserved for monotone behavior.
    if semantic_overlap(next_user_turn, assistant_frame) >= ADOPTION_OVERLAP_THRESHOLD:
        if assistant_frame not in user_map.adopted_frames:
            user_map.adopted_frames.append(assistant_frame)
        return

    # G.8 multi-signal path.
    score, _signals = compute_adoption_score(
        user_map, assistant_frame, next_user_turn,
    )
    if score >= ADOPTION_MULTI_SIGNAL_THRESHOLD:
        if assistant_frame not in user_map.adopted_frames:
            user_map.adopted_frames.append(assistant_frame)


def observe_user_turn(
    user_map: UserMap,
    user_turn_text: str,
    *,
    assistant_previous_frame: Optional[str] = None,
    turn_fit_score: Optional[float] = None,
) -> None:
    """
    One-shot update called per user turn. Updates themes, abstraction baseline,
    adopted/rejected frames, comfort zone, explicit cues, and cold_start.
    """
    user_map.valid_turn_count += 1

    # Explicit cues (CS-4 override feed)
    cues = detect_explicit_cues(user_turn_text)
    for cue in cues:
        if cue not in user_map.framing_preferences:
            user_map.framing_preferences.append(cue)

    # Themes
    update_themes(user_map, user_turn_text, explicit=bool(cues))

    # Abstraction EMA
    update_abstraction_baseline(user_map, user_turn_text)

    # Frame adoption
    if assistant_previous_frame is not None:
        update_frame_adoption(user_map, assistant_previous_frame, user_turn_text)

    # Comfort zone
    if turn_fit_score is not None:
        update_comfort_zone(user_map, turn_fit_score)

    # Confidence grows slowly with adoption evidence and explicit cues
    # Cap: roughly bounded by turn count
    confidence_delta = 0.0
    if cues:
        confidence_delta += 0.06
    if user_map.adopted_frames:
        confidence_delta += 0.04 * min(3, len(user_map.adopted_frames))
    if user_map.valid_turn_count >= 3:
        confidence_delta += 0.02
    user_map.confidence = min(1.0, user_map.confidence + confidence_delta)

    # Refresh cold_start
    update_cold_start(user_map)


# ── Cold-start synthesis policy helpers ─────────────────────────────────────


def cold_start_constraints(user_map: UserMap) -> dict:
    """
    Return a dict describing cold-start synthesis constraints.
    The synthesis/composer layer consumes these.
    """
    if not user_map.cold_start:
        return {
            "allow_bold_reframe": True,
            "halfstep_policy":    "standard",
            "clarification_bias": "normal",
            "deep_preference_inference_allowed": True,
            "style":              "adaptive",
        }
    in_humility_band = user_map.valid_turn_count < HUMILITY_BAND_TURNS
    in_deep_pref_suppression = user_map.valid_turn_count < DEEP_PREF_SUPPRESSION_TURNS
    return {
        "allow_bold_reframe":                False,
        "halfstep_policy":                   "deepening_only",
        "clarification_bias":                "high_if_ambiguous",
        "deep_preference_inference_allowed": not in_deep_pref_suppression,
        "humility_band_active":              in_humility_band,
        "style":                             "neutral_scaffold",
    }
