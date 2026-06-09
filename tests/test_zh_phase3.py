"""Focused regression tests for ZH optimization phase 3.

These tests lock in the four narrow guarantees of phase 3 without pulling
in the full RL runtime:

  1. ZH prose-embedded technical-definition anchors — long ZH prose that
     wraps a clear tech term + definitional intent marker (术语叫做X /
     X这个概念 / X是什么意思 / X的定义 / 怎么理解X) must NOT be routed
     to ask via deictic "这个东西" tails. The anaphora is
     self-contained within the utterance.

  2. ZH ambiguity residuals (prose 56 + continuation 13 = 69 Phase 2):
     (a) super-short bare-verb imperatives ("解决它" / "修复它" / "搞定")
         at turn 0 must ask;
     (b) "解决/修复 + (这|那) + <noun>" deictic short-imperatives must ask;
     (c) prose-embedded 续き/續き/续个故事 (turn-0 continuation) must ask.

  3. ZH freshness: extended concrete-state nouns (研究 / 算法 / 系统 /
     架构 / 模型 / 实验 / 结果 / 收敛速度 / 性能 / 软件) route the
     "最近的X" / "目前X的最Y" / "最近有什么新的X" shapes to verify.
     Stable-definition guard (什么是B树 etc.) preserved.

  4. ZH save-intent prose coverage: 记住/记下/记一下/提醒我/記錄 at
     non-clause-initial positions with mood particles or clear imperative
     suffix fire save intent. False-positive guard (我记得 / 记得要 /
     你记得吗) preserved at "none".

No MMV runtime / GROQ calls required.
"""
from __future__ import annotations

import pytest

from src.kernel.appraisal import Appraiser
from src.kernel.route_decision import select_route
from src.memory.meta_recall import detect_save_intent_strength


# ── 1. ZH prose-embedded technical-definition anchors ──────────────────────

ZH_PROSE_TECH_DEF_NO_ASK = [
    # 13 representative ask-route TD failures from Phase 3 pre baseline.
    "我在学计算机架构的时候看到个术语叫做pipeline怎么理解这个东西",
    "我最近在看一些优化算法的论文，发现他们经常提到pipeline这个概念",
    "我在学习网络协议的时候看到的stream这个词",
    "嘿，我想問一下，有機化合物的定義是什麼呢？",
    "我在学计算机网络的时候看到一个缩写是ICMP，不太懂它到底是什么意思",
    "GAN的mode collapse问题具体是什么",
]


@pytest.mark.parametrize("query", ZH_PROSE_TECH_DEF_NO_ASK)
def test_zh_prose_tech_def_does_not_route_to_ask(query: str) -> None:
    a = Appraiser().evaluate(query)
    d = select_route(a)
    assert d.route != "ask", (
        f"Phase 3: ZH prose-wrapped tech-def should NOT ask: {query!r} "
        f"got route={d.route!r} rc={d.reason_codes}"
    )
    assert "zh_prose_tech_def_anchor" in a.notes, (
        f"Phase 3: ZH_PROSE_TECH_DEF_PATTERN must fire for {query!r}"
    )


# Guard: general ZH ambiguity (NO tech-def anchor) must still ask
ZH_PROSE_TECH_DEF_STILL_ASK = [
    # Phase 2 cases — no tech-term anchor, genuinely ambiguous
    "您好，请继续介绍一下最近的旅行路线",
    "我想看更多关于nosql数据库的优势",
    "我的电脑有问题，帮我解决一下",
    "请帮忙处理一下",
]


@pytest.mark.parametrize("query", ZH_PROSE_TECH_DEF_STILL_ASK)
def test_zh_prose_tech_def_does_not_over_fire(query: str) -> None:
    a = Appraiser().evaluate(query)
    d = select_route(a)
    assert d.route == "ask", (
        f"Phase 3 guard: ZH prose without tech-def anchor must still ask: "
        f"{query!r} got route={d.route!r}"
    )


# ── 2. ZH ambiguity residuals ──────────────────────────────────────────────

ZH_SHORT_BARE_IMPERATIVE_SHOULD_ASK = [
    "解决它",
    "修复它",
    "优化它",
    "搞定",
    "搞定吗",
    "搞定嗎",
    "解决这个问题吧",
    "修復這段文章",
    "修复这张照片的色彩失真吧",
    "优化那个模型吧",
]


@pytest.mark.parametrize("query", ZH_SHORT_BARE_IMPERATIVE_SHOULD_ASK)
def test_zh_short_bare_imperative_asks(query: str) -> None:
    a = Appraiser().evaluate(query)
    d = select_route(a)
    assert d.route == "ask", (
        f"Phase 3: short bare-verb imperative must ask: {query!r} "
        f"got route={d.route!r} rc={d.reason_codes}"
    )


ZH_CONTINUATION_NO_CTX_SHOULD_ASK = [
    "续個故事吧",
    "续き是什么情况",
    "帮我续个故事",
    "幫我續個故事",
]


@pytest.mark.parametrize("query", ZH_CONTINUATION_NO_CTX_SHOULD_ASK)
def test_zh_continuation_no_ctx_asks(query: str) -> None:
    a = Appraiser().evaluate(query)
    d = select_route(a)
    assert d.route == "ask", (
        f"Phase 3: ZH continuation at turn 0 must ask: {query!r} "
        f"got route={d.route!r}"
    )


# ── 3. ZH freshness extended concrete-state nouns ──────────────────────────

ZH_EXTENDED_FRESHNESS_SHOULD_VERIFY = [
    # Research / progress / tech domain
    "我在想化学领域的最新发展",
    "最近的强化学习算法是什么样的",
    "最近的量子纠缠实验结果怎么样",
    "最近量子场理论的研究进展怎么样了",
    "最近的强化学习研究怎么样了",
    # Systems / architecture
    "最近有什么新的分布式文件系统出来了吗",
    "最近的分布式系统怎么样啊",
    "现在分布式系统里面的raft算法到底怎么样",
    # Version / tool / software
    "当前mysql的最高版本是多少",
    # Performance / speed
    "目前梯度下降法的平均收敛速度是多少",
    # Traditional ZH
    "氫的現在價格是多少",
    # Common-use / software
    "您好，请问当前分布式系统中最常用的数据库管理系统是什么",
]


@pytest.mark.parametrize("query", ZH_EXTENDED_FRESHNESS_SHOULD_VERIFY)
def test_zh_extended_freshness_routes_to_verify(query: str) -> None:
    a = Appraiser().evaluate(query)
    d = select_route(a)
    assert d.route == "verify", (
        f"Phase 3: ZH extended freshness must route to verify: {query!r} "
        f"got route={d.route!r} rc={d.reason_codes}"
    )


# Guard: stable-definition ZH queries must NOT be pushed to freshness
ZH_STABLE_DEFINITION_GUARD = [
    "解释一下梯度下降的原理",
    "抛硬币的概率是多少",
]


@pytest.mark.parametrize("query", ZH_STABLE_DEFINITION_GUARD)
def test_zh_stable_def_not_forced_to_verify_freshness(query: str) -> None:
    a = Appraiser().evaluate(query)
    # freshness_sensitive must be False for stable-definition queries;
    # the route may still be verify through a different rule (e.g.
    # DEFINITIONAL_NEEDS_EVIDENCE), but NOT via freshness_sensitive.
    assert not a.freshness_sensitive, (
        f"Phase 3 guard: stable-def query freshness_sensitive must be False: "
        f"{query!r}"
    )


# ── 4. ZH save-intent prose-embedded patterns ──────────────────────────────

ZH_SAVE_INTENT_PROSE_SHOULD_FIRE = [
    # G: clause-embedded 记住 + object + mood
    "记住特征值和特征向量的性质吧",
    # H: modal + 帮我/您/你 + 记住 (disambiguated by explicit addressee)
    "能不能帮我记住这些数据",
    "您能帮我记住吗",
    # I: standalone 记一下
    "保存一下吧",
    # J: 记下 + object
    "顺便记下这个问题",
    # K: 提醒我
    "提醒我一下吧",
    # L: 忘了 + 提醒
    "忘了就提醒我一下吧",
    # M/N: traditional 記錄 variants
    "記錄下來",
    "記錄しておいて",
    # O/P/Q: 保存 / 存 variants
    "帮我存下来",
    "请您保存一个有关椭圆曲线加密的关键信息",
    # R: future-intent save
    "我要处理一个机器学习项目需要记住超参数设置",
    # S: aside-save
    "顺便记一下这个时间",
    # T: prose-embedded 保存
    "请您保存一下这些信息",
    # U: 记下 + deictic object
    "记下这些东西吧",
]


@pytest.mark.parametrize("query", ZH_SAVE_INTENT_PROSE_SHOULD_FIRE)
def test_zh_save_intent_prose_detected(query: str) -> None:
    strength = detect_save_intent_strength(query)
    assert strength != "none", (
        f"Phase 3: ZH save-intent prose pattern must fire: {query!r} "
        f"got strength={strength!r}"
    )


# FP guard for save_intent — must NOT fire on non-save patterns
ZH_SAVE_INTENT_FP_GUARD = [
    "我记得这个",          # self-past
    "我记住了",            # self-past
    "记得要检查输入",      # instructive (imperative to assistant's response)
    "你记得吗",            # question, not save
    "我需要查一下文档",    # task-doing, not save
    "我想要更多信息",      # question, not save
    "自己肯定能记住",      # self-confidence — NOT a request to assistant
    "我能记住这些",        # self-capability assertion
]


@pytest.mark.parametrize("query", ZH_SAVE_INTENT_FP_GUARD)
def test_zh_save_intent_fp_guard_stays_none(query: str) -> None:
    strength = detect_save_intent_strength(query)
    assert strength == "none", (
        f"Phase 3 guard: non-save ZH must NOT fire save-intent: {query!r} "
        f"got strength={strength!r}"
    )


# Existing Phase 1/2 save-intent patterns must keep working
ZH_SAVE_INTENT_PHASE1_2_REGRESSION = [
    "帮我记住这个密码",
    "请记下我的预订号码",
    "希望你能记住我的偏好",
    "今までの話を保存したい",
    "remember my birthday please",
]


@pytest.mark.parametrize("query", ZH_SAVE_INTENT_PHASE1_2_REGRESSION)
def test_phase1_2_save_intent_still_fires(query: str) -> None:
    strength = detect_save_intent_strength(query)
    assert strength in ("strong", "item", "weak_with_context"), (
        f"Phase 1/2 regression: {query!r} got strength={strength!r}"
    )
