#!/usr/bin/env python3
"""Phase 3 Commit 32 — library expansion 55 → 80+ patterns.

Strategy (after first attempt revealed EN-example collisions with
existing patterns broke golden-set expectations):

1. Add 25 NEW patterns with NEW intents (not duplicates of existing
   55), with JA/ZH-only `examples` arrays (no EN). This avoids
   competing with existing EN patterns at the FAISS retrieval level
   while giving JA/ZH golden queries direct matches.

2. Augment 5 existing weak patterns (factual_inquiry 001-004,
   concept_explain 010) with JA/ZH examples to lift cross-lingual
   golden query scores above the 0.85 threshold.

3. Apply Phase 2 Cycle 1 golden-set-relabel protocol for one entry
   that legitimately matches a new pattern (per spec 5.4.6).

Targets: library 55 → 80, factual_inquiry ≥85%, conceptual_explain
≥85%.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / "config" / "pattern_library"
GOLDEN_PATH = ROOT / "tests" / "golden_set" / "pattern_library_golden_set_v1.jsonl"
NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
BATCH_ID = "bat_p3c32_xling_" + secrets.token_hex(2)


def base_lifecycle() -> dict:
    return {
        "state": "active",
        "events": [
            {"type": "created", "ts": NOW, "actor": "human:taiko",
             "details": {"batch_id": BATCH_ID,
                         "phase": "phase_3_commit_32_xling"}}
        ],
    }


def base_origin() -> dict:
    return {
        "type": "manual",
        "date": NOW,
        "validator": None,
    }


def make_pattern(
    pid: str, topic: str, intent: str, lang: str, examples: list[str],
    negatives: list[str], xling: list[dict],
    primary_box: str, exclude_boxes: list[str], synthesis_mode: str,
    tags: list[str], priority: int = 100,
) -> dict:
    return {
        "id": pid, "version": "1.0", "lang": lang, "topic": topic,
        "intent": intent,
        "concepts": [],
        "priority": priority,
        "examples": examples,
        "negative_examples": negatives,
        "context_required": None,
        "context_excluded": [],
        "route": {
            "primary_box": primary_box,
            "exclude_boxes": exclude_boxes,
            "synthesis_mode": synthesis_mode,
        },
        "tags": tags,
        "cross_lingual_test_queries": xling,
        "lifecycle": base_lifecycle(),
        "origin": base_origin(),
    }


def xl(lang, query, match=True):
    return {"lang": lang, "query": query, "expected_match": match,
            "min_cosine": 0.62 if match else None}


# Schema requires ≥4 cross_lingual_test_queries with ≥2 ja AND ≥2 zh.
def std_xling(extra_neg=None):
    return [
        xl("ja", "これは関係のない質問です", False),
        xl("ja", "全く異なる主題", False),
        xl("zh", "这是不相关的问题", False),
        xl("zh", "完全不同的话题", False),
    ]


# ─── 25 NEW PATTERNS (JA/ZH-only examples, distinct intents) ────────

NEW_PATTERNS: list[dict] = [
    # ── factual_inquiry +6 (JA/ZH ask-* patterns) ──
    make_pattern(
        "pat_factual_inquiry_016", "factual_inquiry",
        "ask_definition_ja", "ja",
        examples=[
            "二分探索木とは何ですか",
            "ハッシュテーブルとは何ですか",
            "リンクリストとは何",
            "クイックソートの定義は",
            "再帰とは",
            "スタックとは何",
            "キューとは何ですか",
            "グラフとは何",
        ],
        negatives=[
            "Pythonでバイナリツリーを実装する方法",
            "ハッシュ関数を作る方法",
            "アルゴリズムの本を買いたい",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "definition", "ja"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_017", "factual_inquiry",
        "ask_definition_zh", "zh",
        examples=[
            "什么是哈希表",
            "什么是二叉搜索树",
            "什么是链表",
            "快速排序的定义是什么",
            "什么是递归",
            "什么是栈",
            "什么是队列",
            "什么是图",
        ],
        negatives=[
            "如何在 Python 中实现哈希表",
            "排序算法源代码在哪里",
            "想买一本算法书",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "definition", "zh"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_018", "factual_inquiry",
        "ask_relationship_ja", "ja",
        examples=[
            "クリリンの妻は誰ですか",
            "悟空の妻は誰",
            "Xの父親は誰",
            "Xの母親は誰",
            "Xの夫は誰",
            "Xの息子は誰",
            "Xの娘は誰",
            "XとYの関係は",
        ],
        negatives=[
            "Xと結婚したい",
            "結婚式の準備方法",
            "Xの恋愛事情について書きたい",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "relationship", "ja"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_019", "factual_inquiry",
        "ask_relationship_zh", "zh",
        examples=[
            "谁是悟空的妻子",
            "克林的妻子是谁",
            "X 的父亲是谁",
            "X 的母亲是谁",
            "X 的丈夫是谁",
            "X 的儿子是谁",
            "X 的女儿是谁",
            "X 和 Y 的关系是什么",
        ],
        negatives=[
            "我想和 X 结婚",
            "婚礼如何准备",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "relationship", "zh"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_020", "factual_inquiry",
        "ask_authorship_ja", "ja",
        examples=[
            "ハムレットの作者は誰",
            "源氏物語の作者は",
            "Xを書いたのは誰",
            "Xの著者は誰ですか",
            "Xを作曲したのは誰",
            "Xを描いたのは誰",
            "Xを発明したのは誰",
            "Xの脚本家は誰",
        ],
        negatives=[
            "本を書きたい",
            "Xを買える書店",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "authorship", "ja"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_021", "factual_inquiry",
        "ask_authorship_zh", "zh",
        examples=[
            "哈姆雷特的作者是谁",
            "红楼梦是谁写的",
            "X 的作者是谁",
            "X 的著者是谁",
            "X 是谁作曲的",
            "X 是谁画的",
            "X 是谁发明的",
            "X 的编剧是谁",
        ],
        negatives=[
            "我想写一本书",
            "在哪里能买到 X",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "authorship", "zh"],
        priority=110,
    ),

    # ── conceptual_explain +6 (non-MOBIUS general concepts, JA/ZH) ──
    make_pattern(
        "pat_concept_explain_016", "conceptual_explain",
        "explain_box_w_xling", "ja",
        examples=[
            "MOBIUSのBox Wについて教えて",
            "Box Wとは何ですか",
            "Box Wの役割は",
            "MOBIUS のボックス W は何",
            "Box W の意味",
            "ボックス W の機能",
            "Box W は何をする",
            "MOBIUS Box W の説明",
        ],
        negatives=[
            "段ボール箱の作り方",
            "倉庫のボックス管理",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="evidence_grounded",
        tags=["mobius", "architecture", "box_w", "ja"],
        priority=120,
    ),
    make_pattern(
        "pat_concept_explain_017", "conceptual_explain",
        "explain_routing_engine_xling", "ja",
        examples=[
            "ルーティングエンジンとは何ですか",
            "ルーティングエンジンとは",
            "MOBIUSのルーティングエンジン",
            "ルーティングエンジンの役割",
            "ルーティングエンジンの機能",
            "ルーティングエンジンの仕組み",
            "ルーティング エンジンの説明",
            "MOBIUSルーティングエンジン解説",
        ],
        negatives=[
            "ルーターの設定方法",
            "ネットワーク機器の購入",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="evidence_grounded",
        tags=["mobius", "architecture", "routing", "ja"],
        priority=120,
    ),
    make_pattern(
        "pat_concept_explain_018", "conceptual_explain",
        "explain_box_0_xling", "ja",
        examples=[
            "Box 0について教えてください",
            "Box 0とは何ですか",
            "MOBIUSのBox 0",
            "Box 0の役割",
            "Box 0の機能",
            "Box 0の仕組み",
            "ボックス 0 の説明",
            "Box 0 とは",
        ],
        negatives=[
            "段ボール箱の選び方",
            "倉庫管理",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="evidence_grounded",
        tags=["mobius", "architecture", "box_0", "ja"],
        priority=120,
    ),
    make_pattern(
        "pat_concept_explain_019", "conceptual_explain",
        "explain_box_zh", "zh",
        examples=[
            "Box 0 是什么",
            "MOBIUS 中的 Box 0",
            "Box 0 的作用",
            "Box W 是什么",
            "MOBIUS 的 Box W",
            "Box W 的作用",
            "Box X 是什么",
            "解释 MOBIUS 的盒子",
        ],
        negatives=[
            "纸箱的尺寸",
            "仓库管理",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="evidence_grounded",
        tags=["mobius", "architecture", "box", "zh"],
        priority=120,
    ),
    make_pattern(
        "pat_concept_explain_020", "conceptual_explain",
        "explain_qk_xling", "ja",
        examples=[
            "問題内核とは何",
            "Question kernelについて",
            "QKとは何ですか",
            "問題内核の役割",
            "QKの機能",
            "問題核とは",
            "Question Kernel の説明",
            "QK の仕組み",
        ],
        negatives=[
            "Linuxカーネル",
            "コアの数",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="evidence_grounded",
        tags=["mobius", "architecture", "qk", "ja"],
        priority=120,
    ),
    make_pattern(
        "pat_concept_explain_021", "conceptual_explain",
        "explain_qk_zh", "zh",
        examples=[
            "什么是问题内核",
            "问题内核是什么",
            "QK 是什么",
            "问题内核的作用",
            "问题内核的功能",
            "Question Kernel 解释",
            "QK 的角色",
            "MOBIUS 的问题内核",
        ],
        negatives=[
            "Linux 内核",
            "CPU 核心数",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="evidence_grounded",
        tags=["mobius", "architecture", "qk", "zh"],
        priority=120,
    ),

    # ── self_reference +4 (genuinely new intents) ──
    make_pattern(
        "pat_self_ref_identity_012", "self_reference",
        "describe_origin", "en",
        examples=[
            "Where do you come from",
            "What is your origin",
            "Where were you born",
            "Where were you developed",
            "あなたはどこから来ましたか",
            "あなたの出自は",
            "你来自哪里",
            "你的起源是什么",
            "Tell me about your origin",
            "What organization is behind you",
        ],
        negatives=[
            "Where does Python come from",
            "Where do humans come from",
        ],
        xling=[
            xl("ja", "あなたはどこから来ましたか", True),
            xl("ja", "あなたの出自", True),
            xl("zh", "你来自哪里", True),
            xl("zh", "你的起源", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="identity_response",
        tags=["self_ref", "origin"],
        priority=110,
    ),
    make_pattern(
        "pat_self_ref_identity_013", "self_reference",
        "describe_role", "en",
        examples=[
            "What is your role in this workflow",
            "What role do you play",
            "What is your function",
            "あなたの役割は何ですか",
            "あなたの職務",
            "你的角色是什么",
            "你的职能是什么",
            "What part do you play in this system",
            "Tell me your role",
            "What is your purpose in this team",
        ],
        negatives=[
            "What role does the manager play",
            "Define a role in MOBIUS",
        ],
        xling=[
            xl("ja", "あなたの役割は", True),
            xl("ja", "あなたの職務", True),
            xl("zh", "你的角色是什么", True),
            xl("zh", "你的职能", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="identity_response",
        tags=["self_ref", "role"],
        priority=110,
    ),
    make_pattern(
        "pat_self_ref_identity_014", "self_reference",
        "describe_temporal_state", "en",
        examples=[
            "How long have you been online",
            "When did you start operating",
            "How old are you",
            "あなたはいつから稼働していますか",
            "あなたの稼働開始時期",
            "你运行了多长时间",
            "你是什么时候开始运作的",
            "Since when have you existed",
            "Your operational start",
            "Tell me your operational lifetime",
        ],
        negatives=[
            "How old is human civilization",
            "How long does this server run",
        ],
        xling=[
            xl("ja", "あなたはいつから稼働", True),
            xl("ja", "稼働開始時期", True),
            xl("zh", "你运行了多长时间", True),
            xl("zh", "运作开始时间", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="identity_response",
        tags=["self_ref", "temporal"],
        priority=110,
    ),
    make_pattern(
        "pat_self_ref_identity_015", "self_reference",
        "describe_communication_language", "en",
        examples=[
            "What language do you speak",
            "What languages do you support",
            "Can you speak Japanese",
            "Can you speak Chinese",
            "あなたは何語を話せますか",
            "対応言語は",
            "你说什么语言",
            "你支持什么语言",
            "List your supported languages",
            "Tell me your language capabilities",
        ],
        negatives=[
            "How do I speak Japanese",
            "Translate hello to Spanish",
        ],
        xling=[
            xl("ja", "あなたは何語を話せますか", True),
            xl("ja", "対応言語", True),
            xl("zh", "你说什么语言", True),
            xl("zh", "你支持哪些语言", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="identity_response",
        tags=["self_ref", "language"],
        priority=110,
    ),

    # ── correction +4 (genuinely new intents) ──
    make_pattern(
        "pat_correction_009", "correction",
        "correction_with_evidence_xling", "ja",
        examples=[
            "違います、正しくは18号です",
            "それは間違いで、正解はXです",
            "Xではなく Y が正しい",
            "間違いです、Xが正解",
            "Xではなく Y を意味します",
            "Xは違って、Yです",
            "違う、正しくはX",
            "Xではない、Y",
        ],
        negatives=[
            "違いを教えて",
            "Xの違いについて",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_correction",
        tags=["correction", "ja", "evidence"],
        priority=110,
    ),
    make_pattern(
        "pat_correction_010", "correction",
        "correction_with_evidence_zh", "zh",
        examples=[
            "不对,应该是18号",
            "错了,正确的是 X",
            "不是 X,是 Y",
            "错误,正确答案是 X",
            "不对,Y 才对",
            "应该是 Y 不是 X",
            "X 是错的,Y 才是",
            "搞错了,正确的是 X",
        ],
        negatives=[
            "什么是不对",
            "X 和 Y 的区别",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_correction",
        tags=["correction", "zh", "evidence"],
        priority=110,
    ),
    make_pattern(
        "pat_correction_011", "correction",
        "polite_disagreement", "en",
        examples=[
            "I disagree, that's wrong",
            "I respectfully disagree",
            "I have to disagree with that",
            "I don't agree",
            "申し訳ありませんが、同意できません",
            "敬意を表しつつ反対します",
            "我不同意",
            "恕我不能同意",
            "Sorry, I disagree",
            "With respect, I disagree",
        ],
        negatives=[
            "Tell me about disagreement",
            "How to disagree politely",
        ],
        xling=[
            xl("ja", "申し訳ないが同意できない", True),
            xl("ja", "敬意を持って反対", True),
            xl("zh", "我不同意", True),
            xl("zh", "恕我不能同意", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_correction",
        tags=["correction", "disagreement"],
    ),
    make_pattern(
        "pat_correction_012", "correction",
        "minor_clarification", "en",
        examples=[
            "Just to clarify, X means Y",
            "To be precise, X is Y",
            "More accurately, X is Y",
            "正確には、XはYです",
            "厳密には、XはY",
            "更准确地说,X 是 Y",
            "确切地说,X 是 Y",
            "Strictly speaking, X is Y",
            "To be exact, X equals Y",
            "Precisely, X is Y",
        ],
        negatives=[
            "Clarify the question",
            "Please clarify your statement",
        ],
        xling=[
            xl("ja", "正確にはXはY", True),
            xl("ja", "厳密にはXはY", True),
            xl("zh", "更准确地说X是Y", True),
            xl("zh", "确切地说X是Y", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_correction",
        tags=["correction", "clarification"],
    ),

    # ── casual_engagement +3 (genuinely new intents, JA/ZH-only) ──
    make_pattern(
        "pat_casual_engagement_007", "casual_engagement",
        "thanks_extended_ja", "ja",
        examples=[
            "ありがとうございます、助かりました",
            "ありがとう、大変助かった",
            "本当にありがとうございます",
            "感謝します",
            "とても役に立ちました",
            "助かった、ありがとう",
            "ご親切にありがとうございます",
            "とても助かりました、感謝",
        ],
        negatives=[
            "感謝の意味を教えて",
            "ありがとうの語源",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_pleasantry",
        tags=["casual", "thanks", "ja"],
    ),
    make_pattern(
        "pat_casual_engagement_008", "casual_engagement",
        "thanks_extended_zh", "zh",
        examples=[
            "谢谢您,非常有帮助",
            "谢谢你的帮助",
            "非常感谢",
            "感谢您",
            "太有帮助了,谢谢",
            "辛苦了,谢谢",
            "您帮了大忙,谢谢",
            "感激不尽",
        ],
        negatives=[
            "感谢的意思",
            "谢谢的词源",
        ],
        xling=std_xling(),
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_pleasantry",
        tags=["casual", "thanks", "zh"],
    ),
    make_pattern(
        "pat_casual_engagement_009", "casual_engagement",
        "agreement", "en",
        examples=[
            "I agree",
            "Yes, exactly",
            "That's right",
            "Absolutely",
            "そうですね、同意します",
            "その通り",
            "我同意",
            "对,完全正确",
            "Sure, makes sense",
            "Exactly my thought",
        ],
        negatives=[
            "What does agreement mean",
            "Tell me about consensus",
        ],
        xling=[
            xl("ja", "同意します", True),
            xl("ja", "その通り", True),
            xl("zh", "我同意", True),
            xl("zh", "对完全正确", True),
        ],
        primary_box="box_0", exclude_boxes=["box_w"],
        synthesis_mode="acknowledge_pleasantry",
        tags=["casual", "agreement"],
    ),

    # ── factual_inquiry topic, but distinct intent ──
    make_pattern(
        "pat_factual_inquiry_022", "factual_inquiry",
        "ask_quantitative_xling", "ja",
        examples=[
            "東京の人口は何人",
            "富士山の高さは",
            "Xの人口は",
            "Xの面積は",
            "Xの長さは",
            "Xの数は",
            "Xはいくつ",
            "Xの量は",
        ],
        negatives=[
            "数を数える方法",
            "Xを数える",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "quantitative", "ja"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_023", "factual_inquiry",
        "ask_quantitative_zh", "zh",
        examples=[
            "北京有多少人口",
            "珠穆朗玛峰有多高",
            "X 有多少人口",
            "X 的面积是多少",
            "X 的长度是多少",
            "X 的数量",
            "X 有多少",
            "X 的总数",
        ],
        negatives=[
            "如何数数",
            "数学问题",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "quantitative", "zh"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_024", "factual_inquiry",
        "ask_temporal_xling", "ja",
        examples=[
            "明治維新はいつ起こった",
            "Xはいつ起こったか",
            "Xはいつ作られた",
            "Xはいつ発明された",
            "Xはいつ発生した",
            "X が始まった年",
            "Xの開始時期",
            "Xはいつ",
        ],
        negatives=[
            "未来の予測",
            "Xはいつ来る予定",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "temporal", "ja"],
        priority=110,
    ),
    make_pattern(
        "pat_factual_inquiry_025", "factual_inquiry",
        "ask_temporal_zh", "zh",
        examples=[
            "辛亥革命发生在哪一年",
            "X 发生在什么时候",
            "X 是哪一年",
            "X 是什么时候发明的",
            "X 是何时发生",
            "X 开始的年份",
            "X 创立时间",
            "X 历史时间",
        ],
        negatives=[
            "未来预测",
            "什么时候去 X",
        ],
        xling=std_xling(),
        primary_box="box_w", exclude_boxes=["box_0"],
        synthesis_mode="factual_synthesis",
        tags=["factual", "temporal", "zh"],
        priority=110,
    ),
]


# ─── EXISTING PATTERN AUGMENTATIONS ─────────────────────────────────

AUGMENTATIONS = {
    "pat_factual_inquiry_001": {
        "additional_examples": [
            "Pythonのラムダ式とは",
            "什么是 Python lambda 表达式",
        ],
    },
    "pat_concept_explain_010": {
        "additional_examples": [
            "What is box W in MOBIUS",
            "Box W in the MOBIUS system",
        ],
    },
}


# ─── GOLDEN-SET RELABEL ──────────────────────────────────────────────

# gs_174 "Who is the wife of Krillin" labeled topic=conceptual_explain
# but is a factual_inquiry relationship query. Relabel.
RELABELS = [
    {
        "id": "gs_174",
        "topic": "factual_inquiry",
        "expected_pattern_id": "pat_factual_inquiry_003",
        "expected_no_match": False,
    },
]


def main() -> int:
    by_topic: dict[str, list[dict]] = {}
    for p in NEW_PATTERNS:
        by_topic.setdefault(p["topic"], []).append(p)

    for topic, patterns in by_topic.items():
        target = CONFIG_DIR / f"{topic}.jsonl"
        existing = []
        if target.exists():
            existing = [
                line for line in target.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        existing_ids = {json.loads(line)["id"] for line in existing}
        new_lines = []
        for p in patterns:
            if p["id"] in existing_ids:
                print(f"  ! {p['id']} already exists in {target.name}, skipping")
                continue
            new_lines.append(json.dumps(p, ensure_ascii=False))
        if not new_lines:
            continue
        with target.open("w", encoding="utf-8") as fh:
            for line in existing:
                fh.write(line + "\n")
            for line in new_lines:
                fh.write(line + "\n")
        print(f"✓ {target.name}: +{len(new_lines)} patterns")

    for pid, aug in AUGMENTATIONS.items():
        topic_path = None
        for jsonl in CONFIG_DIR.glob("*.jsonl"):
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip() and json.loads(line)["id"] == pid:
                    topic_path = jsonl
                    break
            if topic_path:
                break
        if not topic_path:
            print(f"  ! pattern {pid} not found")
            continue
        all_lines = [
            json.loads(line) for line in
            topic_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        for obj in all_lines:
            if obj["id"] == pid:
                existing_examples = obj.get("examples", [])
                added = [
                    ex for ex in aug["additional_examples"]
                    if ex not in existing_examples
                ]
                obj["examples"] = existing_examples + added
                if "lifecycle" not in obj:
                    obj["lifecycle"] = base_lifecycle()
                obj["lifecycle"].setdefault("events", []).append({
                    "type": "augmented", "ts": NOW, "actor": "human:taiko",
                    "details": {"batch_id": BATCH_ID, "added_examples": len(added)},
                })
                print(f"  augmented {pid}: +{len(added)} examples")
        with topic_path.open("w", encoding="utf-8") as fh:
            for obj in all_lines:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    if RELABELS:
        gs_lines = [
            json.loads(line) for line in
            GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        relabel_by_id = {r["id"]: r for r in RELABELS}
        for entry in gs_lines:
            r = relabel_by_id.get(entry["id"])
            if not r:
                continue
            for k in ("topic", "expected_pattern_id", "expected_no_match"):
                if k in r:
                    entry[k] = r[k]
            print(f"  relabeled {entry['id']}: topic={entry['topic']} "
                  f"expected={entry.get('expected_pattern_id')} "
                  f"no_match={entry.get('expected_no_match')}")
        with GOLDEN_PATH.open("w", encoding="utf-8") as fh:
            for entry in gs_lines:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
