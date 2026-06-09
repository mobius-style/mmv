from __future__ import annotations

from .appraisal import AppraisalState
from .route_decision import AnswerShape


def select_answer_shape(appraisal: AppraisalState) -> AnswerShape:
    if appraisal.uncertainty <= 0.35 and appraisal.intent_clarity >= 0.75:
        return "low_movement_answer"
    return "admissible_reframing_answer"
