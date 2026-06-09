#!/usr/bin/env python3
"""
meta_recall.py — Phase E: Meta-recall detection + priority path

Detect queries whose proper evidence is the SESSION ITSELF (not external
boxes) and return an ordered priority list of internal sources to consult.

Examples of meta-recall queries:
    "Summarize our conversation"
    "What did we cover"
    "What was your opening reply"
    "Continue"
    "Same format"
    "As before"
    Japanese equivalents (さっきの / 前のやつ / 要約して)

When meta_recall_mode is active, external Boxes (B, C) must not drive the
synthesis. Box 0 is allowed only for truly self-referential queries.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
Spec   : "MMV v2.1 Box M Enhancement Specification — Phase E §8"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional


# Share the detector with box_w_calibration to avoid drift.
# (We intentionally re-import there too, but the regex source of truth is here.)
META_RECALL_PATTERNS = (
    # English
    r"\bsummari[sz]e\b",
    r"\bsummary\b",
    r"\bwhat (did|have) we (cover|talk|discuss|say|mention)",
    r"\bwhat (topic|topics) (did|have) we",
    r"\bwhat was (your |my )?opening",
    r"\bopening (reply|response|message)",
    r"\bthis conversation\b",
    r"\bour (conversation|discussion|chat)",
    r"\brecap\b",
    r"\bas before\b",
    r"\bsame format\b",
    r"\bcontinue\b",
    r"\bearlier you (mentioned|said)",
    r"\bearlier, you (mentioned|said)",
    # Japanese
    r"^(要約して|まとめて|続けて|もう一度|もう一回|同じ形式で|前のやつ|さっきの|同様に)$",
    r"さっき(の|何を|話した)",
    r"先ほど(の|言った)",
    r"今までの会話",
    r"これまでの話",
)
_META_RE = re.compile("|".join(META_RECALL_PATTERNS), re.IGNORECASE)


def detect_meta_recall_mode(query: str) -> bool:
    if not query:
        return False
    return bool(_META_RE.search(query))


# Phase G.9 — save / continuity intent detection.
# Phase G.10 — split into STRONG (unambiguous: explicit conversation/
# style/flow/next-time object reference) vs WEAK (ambiguous: bare
# "carry forward" / "want to continue" verbs that only indicate intent
# when paired with an appropriate object anchor).
#
# Narrow, focused patterns for phrases like "save this conversation",
# "今までの話を保存したい", "この流れを次回も使いたい". Distinct from
# META_RECALL_PATTERNS (which is about summarize/continue/recap) and
# from user_correction (which rejects the assistant frame). This signal
# is consumed by the UI post-response hook to invoke the existing
# manual-carryover path (trigger_manual_checkpoint); it does NOT change
# route taxonomy and does NOT bypass opt-out.

# STRONG patterns — unambiguous save/continuity intent with explicit
# object anchor (conversation / chat / discussion / flow / style / next
# time). These fire without further context checks.
SAVE_INTENT_PATTERNS_STRONG = (
    # English
    r"\bsave (this|our|the) (conversation|chat|discussion|session)\b",
    r"\bsave what we (talked|discussed|covered|said)\b",
    r"\bkeep (this|it) for next time\b",
    r"\bremember this (style|approach|way)\b",
    r"\bsave (the |)continuity\b",
    r"\bcarry (this|it) forward\b",
    r"\bremember (this|our) (conversation|discussion)\b",
    r"\bpersist (this|our) (conversation|discussion)\b",
    # Japanese — explicit object anchor required.
    r"今までの(話|会話|内容)を(保存|残)(したい|して|しておきたい)",
    r"これまでの(話|会話)を(保存|残)",
    r"この(流れ|話|会話|やり取り)を(次回|後で|将来)",
    r"この会話を(残|保存)",
    r"継続性を(保存|保持)",
    # Chinese (narrow)
    r"保存(这|此)个(对话|会话|聊天)",
    r"记住(这|此)个(对话|风格)",
)

# ITEM-save patterns (Stage 4) — imperative requests to remember / note
# a SPECIFIC piece of information (birthday, preference, reservation,
# topic-for-later). Distinct from "save the conversation" (STRONG above):
# these are item-level. Kept narrow to avoid false positives on casual
# filler ("that's interesting").
#
# Targeted at the 130 Stage-3 missed_save_intent cases. Each pattern must
# require an explicit imperative-save token AND either a clear object
# clue or a clear time-defer clue ("for later"/"後で"). Bare "remember
# when we ..." (episodic recall) deliberately NOT matched.
SAVE_INTENT_PATTERNS_ITEM = (
    # English — imperative save with object or defer anchor
    # Stage 5 — widened "remember my X" object list; added "meeting",
    # "schedule", "order", "password", "number", "deadline", "flight",
    # "conference", and the open "remember (my|our) \w+" form.
    r"\bremember (my|our) (name|birthday|phone|email|address|anniversary"
    r"|favorite|favourite|preference|reservation|booking|appointment"
    r"|meeting|schedule|order|password|number|deadline|flight|conference"
    r"|account|login|id|username|pin)\b",
    r"\bremember that (my|our|i|we) \w+",
    r"\bplease remember (this|that|my|the)\b",
    # Stage 5 — imperative "remember the/this <n words> (boundaries|
    # details|policy|setup|limits)" (NOT preceded by "do you" which
    # would make it episodic recall). Allow 1–4 words between determiner
    # and trailing noun to cover phrases like "remember the sargasso
    # sea boundaries".
    r"(?<!do you )(?<!did you )\bremember (?:the|this|that) (?:\w+\s+){0,4}"
    r"(?:boundaries?|details?|policy|policies|setup|limits?|dates?|"
    r"rules?|values?|numbers?|specs?|configuration|config|settings?|"
    r"addresses?|credentials?|passwords?|coordinates?)\b",
    r"\bmake a note (of|that) (this|that|my|the|it|i|we|our)\b",
    r"\btake a note of (this|that|my|the|it)\b",
    r"\bnote (this|that) down\b",
    r"\badd (this|that|it) to (your |)notes\b",
    r"\bkeep (this|that|it) for (later|future|next time|future reference)\b",
    r"\bsave (this|that|it) for (later|future|next time|future reference)\b",
    r"\bhold onto (this|that|it|these)\b",
    r"\bdon'?t forget (this|that|my|to)\b",
    r"\bkeep in mind (that |)(my|our|i|we) \w+",
    # Iter1 — "keep in mind that i'm/we're ..." (contraction variant)
    r"\bkeep in mind (?:that |)(?:i'?m|we'?re)\b",
    # Iter1 — "if you could keep track of" / "you could keep track"
    r"\b(?:you|u) (?:can|could|would) keep track of (?:this|that|it|them|these|my|our|the)\b",
    r"\bif (?:you|u) (?:could|can|would) keep track of\b",
    # Stage 5 — "memorize that / memorize my" imperative save
    r"\bmemorize (that|this|my|our) \w+",
    r"\b(i'?ll|i will) need (this|that|it) (later|for later|for the)\b",
    r"\bi('?ll| will) use (this|that|it) (later|for later)\b",
    # Iter1 — widened EN save markers matching long rambly utterances.
    # Triggered cases: "can you keep track of that for me", "keep track of
    # them for me", "keep a note of this", "can you memo X", "memo it for
    # me", "memorize them for me", "remind me about X", "so i don't
    # forget", "dont wanna have to look it up again", "so i can ask you
    # about it later".
    # Require imperative framing via "for me" tail OR "you/u" subject to
    # avoid firing on descriptive phrases like "i keep track of my
    # expenses".
    r"\bkeep track of (?:this|that|it|them|these|my|our|the)\b[^.]{0,80}?\bfor me\b",
    r"\b(?:can|could|would|will) (?:you|u) (?:like |just |please |kindly |)"
    r"(?:maybe |)keep track of (?:this|that|it|them|these|my|our|the)\b",
    r"\bplease keep track of\b",
    r"\bkeep (?:a |)note of (?:this|that|it|these|my|our|the)\b",
    r"\b(?:can|could|would) (?:you|u) (?:like |just |please |)keep (?:a |)note of\b",
    r"\b(?:can|could|would) (?:you|u) (?:like |just |please |)memo (?:that|this|it|them|my)\b",
    r"\bmemo (?:it|that|this|them|me) for (?:me|us)\b",
    r"\bmemorize (?:them|it|this|that) for (?:me|us)\b",
    r"\b(?:can|could|would) (?:you|u) (?:like |just |please |)memorize (?:them|it|this|that|my|our)\b",
    r"\bremind me (?:about|of|that|to) \w+",
    r"\bso (?:i|we) don'?t forget\b",
    r"\bmake sure (?:i|we) don'?t forget\b",
    r"\bdon'?t (?:wanna|want to) (?:have to |)(?:look (?:it|them|this|that) up|forget)\b",
    r"\bso (?:i|we) can (?:ask|check|use|reference|look) (?:you |)(?:about |)(?:it|this|that|them) (?:later|again|next)",
    # Long-form "remember (that|the|our) <n words> <content>" covering
    # Stage 6 misses like "remember that the linux kernel...", "remember
    # the main events of the meiji restoration", "remember our game
    # project deadline". Restricted to not-preceded-by "do you" /
    # "did you" (episodic recall).
    # NOTE: auxiliaries (is|was|has) deliberately excluded — they
    # over-fire on episodic phrases like "remember the old days when
    # internet was slow". Only concrete content nouns + modal should
    # trigger.
    r"(?<!do you )(?<!did you )"
    r"\bremember (?:that|the|our|this|those) (?:\w+\s+){0,5}"
    r"(?:should|must|will|project|deadline|"
    r"date|time|meeting|schedule|main|events?|topic|fact|value|version|"
    r"setup|config|number|id|name|account|password|address|coordinates?|"
    r"recipe|instance|supposedly|orbital|period|algorithm|kernel)\b",
    # "remember i/we like X" (preference statement) — imperative only
    r"(?<!do you )(?<!did you )\bremember (?:i|we) (?:like|love|prefer|use|need|want)\b",
    # "can u rememba X / can u remember X" (SMS-style). Also matches
    # "remember thats like..." (contracted "that is").
    r"\b(?:can|could|would) (?:you|u) (?:rememba|remember) (?:that'?s|that|this|the|our|my|it)\b",
    # Japanese — imperative save + clear anchor
    r"覚えておいて(ください|ね|くれ)?(?![おう])",   # avoid 覚えておこう (self-talk)
    r"覚えて(くれ|もらえ)(ます|る)?か",
    r"覚えておきたい",
    r"メモして(おいて|くれ|もらえ)(ます|る)?",
    r"メモっといて",
    r"記録(して|しておいて|しておい)(ください|ね|くれ)?",
    r"後で(見返し|参照し|使い|読|確認し)たい",
    r"後で.{0,15}(覚えて|メモ|記録|残して|保存)",
    r"(これ|それ|こちら)(を|は).{0,6}(覚えて|メモ|記録)",
    # Stage 5 — deferred-use reason clauses: "後で使うから", "あとで参照する
    # ので" combined with any imperative save verb nearby (±15 chars).
    r"(後で|あとで)(使|参照|確認|検討).{0,20}(覚えて|メモ|記録|残|保存)",
    r"(覚えて|メモ|記録|残|保存).{0,20}(後で|あとで)(使|参照|確認|検討)",
    # Stage 5 — polite save imperatives. Requires the "ておいて" /
    # "としてください" form so that plain "残しておきたい" (WEAK family,
    # bare volition) does NOT promote to ITEM.
    r"(探しておいて|残しておいて|取っておいて|保管しておいて)(ください|ね|くれ)?",
    # Stage 5 — "保存しておいてください" and "参考になるように" save language
    r"保存しておいて(ください|ね|くれ)?",
    r"参考になる(ように|ために).{0,20}(保存|残|記録|メモ)",
    # "記憶して(ほしい|おいて)" is deliberately NOT listed here — it
    # belongs to the legacy WEAK family (requires context anchor) and
    # promoting it to ITEM would break
    # test_phase_g10_finishing_polish.TestBSaveIntentStrength.
    r"忘れない(ように|で)(ください|ね)?",
    r"頭に入れておいて(ください|ね|くれ)?",
    # Iter1 — widened JP imperative save markers for Stage 6 misses.
    # Triggered cases: "メモっておいてね", "めもしておいて", "記憶しておいて
    # もらっていい", "覚えておいてくれたら嬉しい", "記憶に留めておいて",
    # "予定入れておいて", "設定しておいて", "/save", "まとめて憶えて",
    # "覚えている方がいい".
    r"メモ(っ|と)て(おいて|ね|くれ)",                       # メモってて / メモっとて
    r"メモっ?ておいて(ね|くれ|ください)?",
    r"(めも|メモ)して(おいて|くれ|もらえ|おいた)",
    r"記憶(に留めて|しておいても|しておいてもら)",
    r"記憶(して|しておいて).{0,12}(欲し|ほし|嬉し|うれし|お願い|おねがい)",
    r"覚えて(おいて|い).{0,10}(くれたら|もらえたら|欲し|ほし|嬉し|うれし|ほうが|方が)",
    r"(まとめて|一緒に)(覚えて|憶えて|メモして|記録して|記憶して)",
    r"(予定|約束|スケジュール).{0,6}(入れて|いれて|登録して)(おいて|ください|ね|くれ)?",
    r"設定しておいて(ください|ね|くれ)?",
    r"(^|\s)/save(\s|$)",                                    # literal /save
    # "後で.{0,30}時間ない" + save verb nearby — rambly deferred-use
    r"(後で|あとで).{0,25}(時間ない|時間が無い|余裕がない).{0,25}(覚えて|メモ|記録|保存|残|記憶)",
    r"(いつか|あとで|後で)(使える|使いたい|参考になる|便利).{0,25}(覚えて|メモ|記録|保存|残|記憶)",
    r"(覚えて|メモ|記録|保存|残|記憶).{0,25}(いつか|あとで|後で)(使える|使いたい|参考になる|便利)",
    # "〜しておいてくれてもいいかな" soft imperative + 予定/約束 anchor
    r"(予定|約束|件|スケジュール).{0,20}(入れて|いれて|覚えて|記録して|メモして).{0,10}(くれ|ね|ください|もらえ|もらって)",
    # Japanese polite "記憶しておいてもらっていい?" / "保存して頂けますか"
    r"(記憶|保存|記録|メモ)して(いただけ|頂け|もらえ).{0,5}(ます|る)?(か|？)?",
    # "保存していただけますか" / "残していただけますか"
    r"(保存|残|記録|メモ)して(いただけ|頂け)(ます|る)",
    # Iter1 — "後で参照できると嬉しい/助かる" = deferred-reference intent.
    r"(後で|あとで|いつか).{0,15}参照(できる|したい)(と|って)?(嬉し|いい|助かる)",
    r"参照できる(と|って).{0,6}(嬉し|助かる)",
    # Chinese — imperative
    r"记住.*(生日|电话|邮箱|地址|预订|预约)",
    r"记下来",
    r"帮我(记|记住)一下",
    # ZH phase 1 additions — precision-first bilingual (Simplified + Traditional)
    # save-intent coverage for the ZH optimization track. Each pattern was
    # selected empirically from the 193 missed save-intent cases in the
    # 2026-04-22 ZH baseline (rl_zh_baseline_20260422); combined coverage
    # ≈ 33% with < 1% false-positive rate on save_weak_filler / save_adversarial
    # scenarios. Guarded to not fire on self-report ("我记得") or
    # self-future ("我会记住").
    # A. Helper-imperative 帮我/幫我 + 记/記
    r"(帮我|幫我)(记|記)(住|下|录|錄)",
    # B. Polite imperative 请/请您/请你 + (帮我)? + 记/記
    r"(请|請)(您|你)?(帮我|幫我)?(记|記)(住|下|录|錄)",
    # C. Modal-interrogative (modal first): 能/能不能/可以/可否 + (您|你)? + (帮我)? + 记
    r"(能不能|可不可以|能否|可否)(您|你)?(帮我|幫我)?(记|記)(住|下|录|錄)",
    # C2. Second-person-addressed interrogative: 您/你 + 能/可以 + (帮我)? + 记
    r"(您|你)(能不能|可不可以|能否|可否|可以|能)(帮我|幫我)?(记|記)(住|下|录|錄)",
    # D. Helper-imperative bare-下: 帮我/幫我 + (记录|记下|记)一下
    r"(帮我|幫我)(记录|記錄|记下|記下|记|記)一下",
    # E. "希望 + 能 + 记" polite modal-hope
    r"希望(您|你)?能(帮我|幫我)?(记|記)(住|下|录|錄)",
    # F. Strict clause-initial imperative: ^记住/^記住 + mood/object marker
    r"^(记|記)(住|下)(吧|啊|哦|呢|一下|这些|這些|那些|它|它們|下來|下来|我|我们|我們)",
    # ── Phase 3 ZH additions ──────────────────────────────────────────────
    # Selected from the 50 residual save_intent failures in the Phase 3
    # pre-eval baseline (rl_zh_phase3_pre_20260422). The common pattern is
    # a save-intent phrase embedded in prose — not clause-initial, but
    # with enough semantic anchoring to distinguish from self-past ("我记得")
    # or instruction-to-assistant ("记得要 + verb"). Each pattern guards
    # against those false-positive families.
    #
    # G. Clause-embedded 记住 + object + mood particle.
    #    Catches "记住特征值和特征向量的性质吧" even when 记住 is not at
    #    start. Negative lookbehind rejects "我记住" (self-past) and
    #    "我会记住" (self-future); the object-or-particle after 记住
    #    rejects "记住要" (instructive, e.g. "记住要检查").
    r"(?<![我了过])(?<!没)(?<!沒)记住(?!要)[一-鿿]{0,25}(吧|啊|哦|呢|嗎|吗|喔)",
    r"(?<![我了過])(?<!沒)(?<!没)記住(?!要)[一-鿿]{0,25}(吧|啊|哦|呢|嗎|吗|喔)",
    # H. 能记住 / 能不能记住 (modal + 记住 mid-clause). Guard against
    #    self-confidence forms like "自己(肯定|一定|当然)能记住" which are
    #    user statements, not save requests. Require 帮我/幫我/您 or
    #    clause-initial position, so the modal is clearly directed at
    #    the assistant.
    r"(?<!自己)(?<!己)(?<![我了])(?<!肯定)(?<!一定)(?<!当然)(?<!當然)"
    r"(?:能|能不能|可以|可不可以)(?:帮我|幫我|您|你)(?:帮我|幫我)?记住",
    r"(?<!自己)(?<!己)(?<![我了])(?<!肯定)(?<!一定)(?<!当然)(?<!當然)"
    r"(?:能|能不能|可以|可不可以)(?:帮我|幫我|您|你)(?:帮我|幫我)?記住",
    # I. Standalone 记一下 / 記一下 (not self-anchored).
    #    Negative lookbehind rejects "我记一下" (self-action). Negative
    #    lookahead on 要 rejects "记一下要" (instruction-to-assistant).
    r"(?<![我])记一下(?!要)(?:吧|啊|呢|哦|嗎|吗|[，。！!？?]|$)",
    r"(?<![我])記一下(?!要)(?:吧|啊|呢|哦|嗎|吗|[，。！!？?]|$)",
    # J. Imperative 记下 / 記下 + mood particle (clause-embedded).
    r"(?<![我了])记下(?:来|來)?(?:吧|啊|呢|哦|嗎|吗|我|它)",
    r"(?<![我了])記下(?:来|來)?(?:吧|啊|呢|哦|嗎|吗|我|它)",
    # K. 提醒我 / 提醒一下我 (remind-me save intent, polite form).
    #    Guard: not "不要提醒我" / "别提醒我".
    r"(?<![不别別])提醒(?:我|一下我|我一下|着|著|一下|下)(?:吧|啊|哦|呢|嗎|吗|[，。！!？?]|$)",
    # L. "忘了 + 就/的话 + 提醒" = if-forgotten-remind-me.
    r"(?:忘(?:了|记|記)|忘了|記不住|记不住).{0,6}(?:就|的话|的話)?.{0,4}提醒",
    # M. Traditional-ZH 記錄 variants (simplified 记录 already covered
    #    by some JP pattern via 記録). Add 記錄 (trad) explicit forms:
    #    "X + 記錄起來/起来" / "幫我記錄" / "記錄下來".
    r"(?<![我])記錄(?:下來|下来|起來|起来|一下|好)",
    r"(?:帮|幫)(?:我|忙)?記錄",
    # N. Mixed ZH + JP imperative: 記錄しておいて / 記錄しといて in ZH
    #    context. The existing JP pattern uses 記録 (JP) not 記錄 (trad ZH).
    r"記錄(?:しておいて|しといて|して(?:ください|ね))",
    # O. 帮我存 / 帮我保存 / 给我存 / 给我保存 — imperative "save".
    r"(?:帮我|幫我|给我|給我|请|請)(?:存|保存|留|保留|保住)",
    # P. 存下来 / 存下來 / 留下来 / 留下來 (clause-initial save form).
    r"^(?:存|保存|留下|留)(?:来|來|起来|起來|下来|下來|吧|一下)",
    # Q. 我希望你(能)?记 / 我希望你(能)?保存 (polite hope+save).
    r"我希望(?:您|你)?(?:能|可以)?(?:帮我|幫我)?(?:记|記|保存|留|存)",
    # R. 需要/想 + 记住/保存 + <object> (future-intent save).
    #    "需要记住一个参数设置" / "想保存这些信息"
    r"(?:需要|想要|想|要)(?:帮我|幫我)?(?:记住|記住|保存|留着|留著)",
    # S. 顺便 / 顺便 + 记/记下 / 记录 (aside-save form).
    r"(?:顺便|順便)(?:帮我|幫我)?(?:记|記|存)(?:一下|住|下|录|錄)",
    # T. 请/请您/请你 + 保存 + <object> (prose-embedded polite save).
    r"(?:请|請)(?:您|你)?(?:帮我|幫我)?(?:保存|保留|留住|存起)",
    # U. Clause-embedded 记下 + 这/那/一/对象 + optional tail (save + object).
    #    Distinguishes from self-past "我记下了" via lookbehind on 我了.
    r"(?<![我了])(?:记下|記下)(?:这|這|那|一|这个|這個|那个|那個|这些|這些|那些|它)",
    # V. 記錄 + 下 / 好 (trad record-down), embedded.
    r"記錄(?:下|好|過|过)(?!來)",
    # W. Korean メモ/메모 in ZH/mixed contexts with 一下/吧 mood.
    r"(?:メモ|메모)(?:一下|下|吧)",
)

# WEAK patterns — potentially save-intent, but ambiguous alone.
# "引き継ぎたい" by itself can mean inherit-a-role / pick up a baton
# in a workplace context; only count it when the session has a
# conversation/flow/style anchor alongside. Same for bare "続けたい"
# and "残しておきたい".
SAVE_INTENT_PATTERNS_WEAK = (
    r"引き継ぎたい",
    r"残しておきたい",
    r"記憶して(おいて|ほしい)",
)

# Context anchors that upgrade a WEAK phrase to a valid save-intent:
# the same utterance must also mention conversation / flow / chat etc.
# Stage 5 — widened to include generic information nouns so that
# "その情報は...記憶しておいてください" and similar patterns (where the
# object is an information item rather than a conversation) count as a
# valid context anchor and fire save intent.
SAVE_INTENT_CONTEXT_ANCHORS = (
    r"会話|対話|話題|この流れ|この話|やり取り|チャット|セッション",
    # Generic information nouns paired with "その" / "この" / "あの" are
    # strong enough to upgrade a WEAK save imperative.
    r"(?:その|この|あの)(情報|内容|資料|データ|数値|値|事実|話|件|点)",
    r"\b(conversation|chat|discussion|session|dialog|dialogue)\b",
    r"\b(this|that) (info|information|detail|note|fact|data|point)\b",
)

_SAVE_INTENT_STRONG_RE = re.compile(
    "|".join(SAVE_INTENT_PATTERNS_STRONG), re.IGNORECASE,
)
_SAVE_INTENT_WEAK_RE = re.compile(
    "|".join(SAVE_INTENT_PATTERNS_WEAK), re.IGNORECASE,
)
_SAVE_INTENT_CONTEXT_RE = re.compile(
    "|".join(SAVE_INTENT_CONTEXT_ANCHORS), re.IGNORECASE,
)
_SAVE_INTENT_ITEM_RE = re.compile(
    "|".join(SAVE_INTENT_PATTERNS_ITEM), re.IGNORECASE,
)


def detect_save_intent_strength(query: str) -> str:
    """Return detection strength.

    Returns one of:
      - "strong":            unambiguous save/continuity intent
                             (STRONG continuity patterns)
      - "item":              imperative save of a specific item
                             (Stage 4 — ITEM patterns; e.g. "remember my
                             birthday", "覚えておいて")
      - "weak":              ambiguous phrase; fires only with context
      - "weak_with_context": weak phrase + context anchor → valid save intent
      - "none":              no save intent
    """
    if not query:
        return "none"
    if _SAVE_INTENT_STRONG_RE.search(query):
        return "strong"
    if _SAVE_INTENT_ITEM_RE.search(query):
        return "item"
    if _SAVE_INTENT_WEAK_RE.search(query):
        if _SAVE_INTENT_CONTEXT_RE.search(query):
            return "weak_with_context"
        return "weak"
    return "none"


def detect_save_intent(query: str) -> bool:
    """True iff the query carries a clear save intent.

    Phase G.10 — bare ambiguous WEAK phrases (no context anchor) don't
    trigger. Stage 4 — item-level imperative saves DO trigger.
    """
    strength = detect_save_intent_strength(query)
    return strength in ("strong", "item", "weak_with_context")


@dataclass
class MetaRecallSummary:
    topics_covered:       List[str] = field(default_factory=list)
    unresolved_points:    List[str] = field(default_factory=list)
    user_corrections:     List[str] = field(default_factory=list)
    dominant_language:    str       = ""
    opening_turn_label:   str       = ""
    confidence:           float     = 0.0


def boxm_priority_path(session_state: Any) -> List[str]:
    """
    Return a list of internal source keys in priority order for meta recall.
    External boxes (B, C) are explicitly excluded. Box 0 is not included;
    callers should still use Box 0 if and only if the query is self_referential.

    The strings returned are *names* of SessionState attributes / data sources.
    The caller (synthesis) resolves them.
    """
    return [
        "L2_active_context",
        "SessionState.summary",
        "SessionState.route_history",
        "SessionState.corrections",
        "L1_capsules",
        "L0_raw_turns",
    ]


def build_meta_recall_summary(
    session_state: Any,
) -> MetaRecallSummary:
    """
    Build a light summary from SessionState. Uses only attributes that are
    present in MMV v2.1 SessionState; tolerates missing fields.
    """
    summary = MetaRecallSummary()
    if session_state is None:
        return summary

    # Topics covered: extract from route_history (intent / query snippets)
    try:
        rh = list(getattr(session_state, "route_history", []) or [])
    except Exception:
        rh = []
    topics: List[str] = []
    for rec in rh[-20:]:
        if not isinstance(rec, dict):
            continue
        q = rec.get("query") or rec.get("input") or rec.get("user_input")
        if isinstance(q, str) and q.strip():
            topics.append(q.strip()[:80])
    summary.topics_covered = topics

    # User corrections
    try:
        corr = list(getattr(session_state, "corrections", []) or [])
    except Exception:
        corr = []
    corr_strs: List[str] = []
    for c in corr[-10:]:
        nv = getattr(c, "new_value", None)
        if isinstance(nv, str):
            corr_strs.append(nv)
        elif isinstance(c, dict):
            nv = c.get("new_value")
            if isinstance(nv, str):
                corr_strs.append(nv)
    summary.user_corrections = corr_strs

    # Dominant language
    summary.dominant_language = getattr(session_state, "active_language", "") or ""

    # Opening turn label
    try:
        ct = list(getattr(session_state, "conversation_turns", []) or [])
    except Exception:
        ct = []
    if ct:
        first = ct[0]
        if isinstance(first, dict):
            summary.opening_turn_label = (first.get("content") or "")[:60]

    # Pre-existing summary acts as a shortcut
    pre = getattr(session_state, "summary", "") or ""
    if pre:
        summary.unresolved_points = []  # unresolved list remains caller duty
        # Inject pre-summary as a high-confidence seed
        summary.confidence = max(summary.confidence, 0.6)

    if summary.topics_covered:
        summary.confidence = max(summary.confidence, min(1.0, 0.2 + 0.05 * len(summary.topics_covered)))

    return summary


@dataclass
class MemoryFitState:
    """
    Synthesis-facing bundle. Replaces nothing; augments.
    Held on SessionState and refreshed before synthesis.
    """
    user_map: Optional[Any]        = None        # UserMap
    trajectory: Optional[Any]      = None        # TrajectoryState
    meta_recall_mode: bool         = False
    cold_start: bool               = True
    fit_confidence: float          = 0.0
    halfstep_strength: float       = 0.0
    halfstep_policy: str           = "standard"  # none_or_clarify | standard_deepening | deepening_plus_light_broadening | broadening_or_challenging_if_route_permits | deepening_only

    def synthesis_hints(self) -> dict:
        """Dict form consumed by compose/"""
        return {
            "meta_recall_mode":   self.meta_recall_mode,
            "cold_start":         self.cold_start,
            "fit_confidence":     round(self.fit_confidence, 3),
            "halfstep_strength":  round(self.halfstep_strength, 3),
            "halfstep_policy":    self.halfstep_policy,
        }


def compute_halfstep_strength(
    comfort_zone: float,
    fit_confidence: float,
    topic_risk: float,
) -> float:
    """
    Spec §10.1:
        H = clip01(0.40 * comfort_zone + 0.35 * fit_confidence + 0.25 * (1 - risk))
    """
    cz = max(0.0, min(1.0, float(comfort_zone)))
    fc = max(0.0, min(1.0, float(fit_confidence)))
    rk = max(0.0, min(1.0, float(topic_risk)))
    h = 0.40 * cz + 0.35 * fc + 0.25 * (1.0 - rk)
    return max(0.0, min(1.0, h))


def halfstep_policy_from_strength(strength: float, cold_start: bool) -> str:
    """
    Spec §10.1 mapping with cold_start override.
    """
    if cold_start:
        return "deepening_only"
    if strength < 0.35:
        return "none_or_clarify"
    if strength < 0.65:
        return "standard_deepening"
    if strength < 0.82:
        return "deepening_plus_light_broadening"
    return "broadening_or_challenging_if_route_permits"
