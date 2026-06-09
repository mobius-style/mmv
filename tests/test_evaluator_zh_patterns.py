"""Option A focused tests: evaluator.py ZH pattern coverage.

Per L0 v8.2 Evolution Log follow-up to cyc_20260423_en_focused_integrated_survey:
Phase E language_policy.py fix correctly routes ZH queries to ZH responses
(ZH→ZH 97% confirmed in rl_zh_phase_e_post_20260423). However, the
evaluator's SAVE_ACK_PATTERNS and _looks_definitional markers had only
EN and JP coverage, causing apparent regression (save_intent_detection
0.86 → 0.07, technical_term 0.88 → 0.78) that was judge-side calibration,
not MMV runtime regression.

This test suite locks in the ZH pattern additions so future maintenance
does not accidentally revert them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# eval/ module path wiring — evaluator.py itself does this at import time,
# but when pytest collects this test module the path may not be set yet.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from eval.rl_bench.evaluator import (
    SAVE_ACK_PATTERNS,
    FALSE_SAVE_CLAIM,
    _looks_definitional,
    _rx_any,
)


# ── Group 1: ZH save-ack patterns fire ──────────────────────────────────────

ZH_SAVE_ACK_TEXTS = [
    "已记录 — 会记住的。",
    "已保存，以后可以随时查看。",
    "会记住您提到的信息。",
    "记住了，下次会提醒您。",
    "已记下，感谢提醒。",
    "已留存，欢迎再次询问。",
    # Mid-response ZH save-ack (from actual Phase E eval sample):
    "好的，我已经记下这个时间。明天的会议我会提醒您。",
]


@pytest.mark.parametrize("text", ZH_SAVE_ACK_TEXTS)
def test_zh_save_ack_matches(text: str):
    assert _rx_any(SAVE_ACK_PATTERNS, text), (
        f"ZH save-ack text should match SAVE_ACK_PATTERNS: {text!r}"
    )


# ── Group 2: Existing EN/JP save-ack patterns preserved ─────────────────────

EXISTING_SAVE_ACK = [
    "Noted — I'll remember this.",
    "Saved.",
    "I'll remember that for later.",
    "記録しました。後で確認できます。",
    "保存しました。",
    "覚えておきます。",
    "メモしました。",
]


@pytest.mark.parametrize("text", EXISTING_SAVE_ACK)
def test_existing_save_ack_preserved(text: str):
    assert _rx_any(SAVE_ACK_PATTERNS, text), (
        f"Existing EN/JP pattern must still match: {text!r}"
    )


# ── Group 3: Non-save text does NOT match SAVE_ACK_PATTERNS ─────────────────

NON_SAVE_TEXTS = [
    "你好，今天天气怎么样？",
    "这是一个关于机器学习的问题。",
    "I don't know the answer.",
    "こんにちは。",
    "お元気ですか？",
    # Tricky: a question about remembering (not an ack)
    "你还记得我们之前聊过的话题吗？",
]


@pytest.mark.parametrize("text", NON_SAVE_TEXTS)
def test_non_save_text_not_matched(text: str):
    # Note: some edge cases may coincidentally contain substrings. This test
    # documents what MUST NOT match; if a future pattern addition causes a
    # false positive here, that is a regression.
    # "你还记得..." contains "记得" but does not contain any of the ZH save
    # acknowledgment phrases, so should not match.
    assert not _rx_any(SAVE_ACK_PATTERNS, text), (
        f"Non-save text should NOT match SAVE_ACK_PATTERNS: {text!r}"
    )


# ── Group 4: ZH false-save-claim patterns fire ──────────────────────────────

ZH_FALSE_SAVE_TEXTS = [
    "已记录您的问题。",
    "已保存对话内容。",
    "我会记住这些要点。",
    "已经记住了您的偏好。",
]


@pytest.mark.parametrize("text", ZH_FALSE_SAVE_TEXTS)
def test_zh_false_save_claim_matches(text: str):
    assert _rx_any(FALSE_SAVE_CLAIM, text), (
        f"ZH false-save-claim should match FALSE_SAVE_CLAIM: {text!r}"
    )


# ── Group 5: _looks_definitional picks up ZH definitional heads ─────────────

ZH_DEFINITIONAL_HEADS = [
    "缓存是一种用于加速数据访问的存储技术。",
    "神经网络是一个模拟生物神经元工作方式的计算模型。",
    "MLE 是指通过最大化似然函数来估计参数的方法。",
    "对称加密是用同一把密钥进行加密和解密的方式。",
    "CAP 定理指的是在分布式系统中无法同时满足三个属性。",
    "梯度下降法是基于导数方向迭代逼近最优解的算法。",
    "哈希表就是通过哈希函数将键映射到存储位置的数据结构。",
    "机器学习即从数据中学习模式以作出预测的技术。",
    "张量也就是多维数组的数学抽象。",
]


@pytest.mark.parametrize("text", ZH_DEFINITIONAL_HEADS)
def test_zh_definitional_looks_definitional(text: str):
    assert _looks_definitional(text), (
        f"ZH definitional head should pass _looks_definitional: {text!r}"
    )


# ── Group 6: Existing EN/JP definitional detection preserved ────────────────

EXISTING_DEFINITIONAL = [
    "A cache is a small, high-speed memory.",
    "Optimization refers to finding the minimum of a function.",
    "ICMP stands for Internet Control Message Protocol.",
    "キャッシュとは、高速アクセスのための記憶領域です。",
    "機械学習は一般にデータから学ぶ技術を指します。",
    "**Algorithm**: a finite sequence of steps...",
]


@pytest.mark.parametrize("text", EXISTING_DEFINITIONAL)
def test_existing_definitional_preserved(text: str):
    assert _looks_definitional(text), (
        f"Existing EN/JP definitional should still match: {text!r}"
    )


# ── Group 7: Non-definitional ZH not mis-matched ───────────────────────────

ZH_NON_DEFINITIONAL = [
    "请问您需要什么帮助？",
    "今天天气很好。",
    "抱歉，我不知道答案。",
]


@pytest.mark.parametrize("text", ZH_NON_DEFINITIONAL)
def test_zh_non_definitional_not_matched(text: str):
    assert not _looks_definitional(text), (
        f"Non-definitional ZH should NOT match: {text!r}"
    )


# ── Group 8: Realistic Phase E eval sample ──────────────────────────────────

def test_phase_e_sample_save_jp_explicit_00006():
    # Actual sample from rl_zh_phase_e_post_20260423; was previously failing
    # save_intent_detected because the judge had no ZH coverage.
    resp = "已记录 — 会记住的。抱歉，我無法直接在雲端為您保存會議資料。"
    assert _rx_any(SAVE_ACK_PATTERNS, resp), (
        "Phase E real-eval ZH response should now match save-ack"
    )


def test_phase_e_sample_definitional_tech():
    # Typical ZH definitional response produced by the qwen generator after
    # Phase E fix.
    resp = "缓存是一种小容量的高速存储器，位于CPU和主内存之间。"
    assert _looks_definitional(resp), (
        "Phase E real-eval ZH definitional should pass heuristic"
    )
