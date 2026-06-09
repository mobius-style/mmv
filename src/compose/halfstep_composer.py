"""
halfstep_composer.py — HalfStep mathematical-model-based instructions.

Mathematical basis (Constitutional Core section 7):
  - Conceptual distance = exactly 1 unit per turn
  - The system performs the twist; the leap belongs to the user
  - Embed within answer structure; never append as trailing sentence

HalfStep applies to: answer route and verify route (post-synthesis).
HalfStep does NOT apply to: ask route or abstain route.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

from typing import Literal

HalfStepType = Literal[
    "hidden_assumption",
    "adjacent_contrast",
    "missing_constraint",
    "teaching_scaffold",
]

_HALFSTEP_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "en": {
        "hidden_assumption": (
            "surface one unstated premise within your answer structure "
            "(conceptual distance = 1 unit; "
            "do not state it as a trailing sentence — "
            "weave it into the answer so the user encounters it naturally; "
            "the twist is yours, the leap belongs to the user)"
        ),
        "adjacent_contrast": (
            "embed one closely related alternative framing at exactly "
            "1 conceptual unit of distance — "
            "close enough for the user to own, far enough to induce movement; "
            "do not append it separately at the end"
        ),
        "missing_constraint": (
            "identify one missing condition that would sharpen the answer — "
            "phrase it as a natural part of your response, "
            "not as a trailing question; distance = 1 unit"
        ),
        "teaching_scaffold": (
            "provide one structural step toward the next question — "
            "assimilable, not a full abstraction leap; "
            "embed within the answer, do not append separately"
        ),
    },
    "ja": {
        "hidden_assumption": (
            "回答の構造の中に、問いが前提としている事柄を一つ自然に織り込む "
            "（概念的距離=1単位；末尾に別途付け加えない；"
            "ひねりはシステムが行い、跳躍はユーザーが行う）"
        ),
        "adjacent_contrast": (
            "回答の中に、1単位の概念的距離で隣接する別の切り口を一つ埋め込む；"
            "末尾に別途付け加えない"
        ),
        "missing_constraint": (
            "回答の中で、答えをより精確にする条件を一つ自然に示す；"
            "末尾に質問として付け加えない"
        ),
        "teaching_scaffold": (
            "次の問いへの一つの足がかりを回答の中に埋め込む；"
            "抽象の大きな跳躍ではなく、1単位の近い移動"
        ),
    },
    "zh": {
        "hidden_assumption": (
            "在答案结构中自然织入问题所隐含的一个前提 "
            "（概念距离=1单位；不要单独附在末尾；"
            "扭转由系统完成，跳跃由用户完成）"
        ),
        "adjacent_contrast": (
            "在答案中嵌入一个距离恰好1单位的相邻视角；不要单独附在末尾"
        ),
        "missing_constraint": (
            "在答案中自然指出一个能使答案更精确的缺失条件；"
            "不要作为尾部问题附加"
        ),
        "teaching_scaffold": (
            "在答案中嵌入通向下一个问题的一个结构性步骤；"
            "近距离移动，而非大幅跳跃"
        ),
    },
}


def compose_halfstep(kind: HalfStepType, user_language: str = "en") -> str:
    """
    Return a HalfStep instruction based on the mathematical principle.

    Mathematical basis (Constitutional Core section 7):
      - conceptual distance = exactly 1 unit per turn
      - The system performs the twist; the leap belongs to the user
      - Embed within answer structure; never append as trailing sentence

    HalfStep applies to: answer route and verify route (post-synthesis).
    HalfStep does NOT apply to: ask route or abstain route.

    The returned string is inserted into routing_engine.py as:
      f"After answering, add one brief reflective note: {result}"
    Design the return value to be semantically coherent in that context.
    """
    lang_map = _HALFSTEP_INSTRUCTIONS.get(
        user_language, _HALFSTEP_INSTRUCTIONS["en"]
    )
    return lang_map.get(kind, lang_map["hidden_assumption"])
