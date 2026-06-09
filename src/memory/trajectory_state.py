#!/usr/bin/env python3
"""
trajectory_state.py — Phase E L3: TrajectoryState

Lightweight per-session trajectory tracker. Holds a small observation log that
drives half-step strength decisions and UserMap confidence growth. Not meant
to be persisted across sessions by default.

Non-goals:
    - Not an audit log
    - Not a personality / emotion tracker
    - Not a replacement for SessionState.route_history

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "MMV v2.1 Box M Enhancement Specification — Phase E"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TrajectoryState:
    session_id:         str                = ""
    turn_index:         int                = 0
    abstraction_shift:  List[float]        = field(default_factory=list)
    twist_history:      List[str]          = field(default_factory=list)
    leap_history:       List[str]          = field(default_factory=list)
    adoption_notes:     List[str]          = field(default_factory=list)
    correction_notes:   List[str]          = field(default_factory=list)

    # Half-step observation counters (used by over-leading guard)
    halfstep_adopted_count:    int = 0
    halfstep_corrected_count:  int = 0
    halfstep_last_frame:       Optional[str] = None

    def record_turn(
        self,
        abstraction_value: Optional[float] = None,
        twist: Optional[str] = None,
        leap: Optional[str] = None,
        adoption: Optional[str] = None,
        correction: Optional[str] = None,
    ) -> None:
        self.turn_index += 1
        if abstraction_value is not None:
            self.abstraction_shift.append(float(abstraction_value))
        if twist:
            self.twist_history.append(twist)
        if leap:
            self.leap_history.append(leap)
        if adoption:
            self.adoption_notes.append(adoption)
        if correction:
            self.correction_notes.append(correction)

    def record_halfstep_outcome(
        self,
        adopted: bool = False,
        corrected: bool = False,
        frame: Optional[str] = None,
    ) -> None:
        if adopted:
            self.halfstep_adopted_count += 1
        if corrected:
            self.halfstep_corrected_count += 1
        self.halfstep_last_frame = frame

    def over_leading_rate(self) -> float:
        """Proportion of half-steps that led to corrections."""
        total = self.halfstep_adopted_count + self.halfstep_corrected_count
        if total == 0:
            return 0.0
        return self.halfstep_corrected_count / total

    def summary(self) -> dict:
        return {
            "turn_index":                self.turn_index,
            "halfstep_adopted_count":    self.halfstep_adopted_count,
            "halfstep_corrected_count":  self.halfstep_corrected_count,
            "over_leading_rate":         round(self.over_leading_rate(), 3),
            "correction_notes":          list(self.correction_notes[-5:]),
            "adoption_notes":            list(self.adoption_notes[-5:]),
        }
