#!/usr/bin/env python3
"""
generate_qk_minority.py — Generate QK-minority samples to balance the QK index.

Target: ~900 samples
  abstain:      ja/en/zh x 100 = 300
  bounded-only: ja/en/zh x 100 = 300
  high-TVS:     ja/en/zh x 100 = 300

Uses qwen3.5:9b via Ollama /api/chat (think:false).
Output: data/raf/qk_supplement.jsonl

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"
OUTPUT = ROOT / "data" / "raf" / "qk_supplement.jsonl"

BATCH_SIZE = 20
BATCHES_PER_COMBO = 5  # 5 batches x 20 = 100 per lang/category

# ── Prompts ──────────────────────────────────────────────────────────────────

PROMPTS = {
    "abstain": {
        "ja": (
            "以下の条件を満たす日本語のクエリを20件生成してください。\n"
            "条件: AIが原理的に回答できないクエリ。具体的には:\n"
            "- 発話者の個人的な現在状況（今日の天気、今夜の食事、自分の気持ち）\n"
            "- リアルタイムの個人データ（自分のスケジュール、位置情報）\n"
            "- AIが知り得ない特定個人の私的情報\n"
            'JSON配列で返してください: ["query1", "query2", ...]'
        ),
        "en": (
            "Generate 20 queries in English that an AI fundamentally cannot answer because they require:\n"
            "- The user's personal real-time context (today's weather at their location, what they had for lunch)\n"
            "- Private personal data only the user knows\n"
            "- Real-time system state the AI has no access to\n"
            'Return as JSON array: ["query1", "query2", ...]'
        ),
        "zh": (
            "请生成20个中文查询，这些查询是AI原则上无法回答的，因为它们需要：\n"
            "- 用户的个人实时情况（今天的天气、今晚吃什么）\n"
            "- 只有用户本人才知道的私人信息\n"
            '以JSON数组返回：["query1", "query2", ...]'
        ),
    },
    "bounded-only": {
        "ja": (
            "以下の条件を満たす日本語のクエリを20件生成してください。\n"
            "条件: AIは回答できるが、知識カットオフの制約を明示する必要があるクエリ。\n"
            "- 「最新の〜は何ですか」「現在の〜の状況は」\n"
            "- 直近の選挙結果、最新モデル、現在の価格など\n"
            "- 「私の知識は〜時点まで」という断り書きが必要\n"
            'JSON配列で返してください: ["query1", "query2", ...]'
        ),
        "en": (
            "Generate 20 English queries where an AI can attempt an answer but must explicitly "
            "acknowledge knowledge cutoff limitations:\n"
            "- Questions about 'current', 'latest', 'most recent' facts that change over time\n"
            "- Recent election results, newest AI models, current prices, ongoing conflicts\n"
            'Return as JSON array: ["query1", "query2", ...]'
        ),
        "zh": (
            "请生成20个中文查询，AI可以尝试回答但必须明确说明知识截止日期的限制：\n"
            "- 关于'最新'、'当前'、'目前'的事实性问题\n"
            "- 最近的选举结果、最新AI模型、当前价格\n"
            '以JSON数组返回：["query1", "query2", ...]'
        ),
    },
    "high-tvs": {
        "ja": (
            "以下の条件を満たす日本語のクエリを20件生成してください。\n"
            "条件: 情報の鮮度が非常に重要なクエリ（時間経過で内容が大きく変わる）。\n"
            "- AIの最新動向、最新技術、最新研究\n"
            "- 現在進行中の社会問題、政策、経済状況\n"
            'JSON配列で返してください: ["query1", "query2", ...]'
        ),
        "en": (
            "Generate 20 English queries where temporal freshness is critical - "
            "the answer changes significantly over short periods:\n"
            "- Rapidly evolving fields: AI capabilities, geopolitics, financial markets\n"
            "- Ongoing events, current research frontiers, recent breakthroughs\n"
            'Return as JSON array: ["query1", "query2", ...]'
        ),
        "zh": (
            "请生成20个中文查询，这些查询的时效性非常重要（信息随时间快速变化）：\n"
            "- AI最新进展、最新技术、最新研究\n"
            "- 正在进行的社会问题、政策、经济形势\n"
            '以JSON数组返回：["query1", "query2", ...]'
        ),
    },
}

# ── Label assignments ────────────────────────────────────────────────────────

LABEL_MAP = {
    "abstain":      {"qk_entitlement": "abstain",      "qk_tvs_estimate": "low"},
    "bounded-only": {"qk_entitlement": "bounded-only", "qk_tvs_estimate": "high"},
    "high-tvs":     {"qk_entitlement": "answerable",   "qk_tvs_estimate": "high"},
}


def call_ollama(prompt: str, retries: int = 1) -> list[str]:
    """Call Ollama and parse JSON array of query strings."""
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.9, "num_predict": 2048},
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json()["message"]["content"].strip()

            # Extract JSON array from response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                arr = json.loads(text[start:end])
                if isinstance(arr, list):
                    return [str(q).strip() for q in arr if q and str(q).strip()]

            # Fallback: try line-by-line
            lines = [l.strip().strip('"').strip("'").strip(",") for l in text.splitlines()
                     if l.strip() and not l.strip().startswith(("[", "]", "```"))]
            if lines:
                return lines[:BATCH_SIZE]

        except Exception as e:
            if attempt < retries:
                print(f"    Retry ({e})...")
                time.sleep(2)
                continue
            print(f"    Failed: {e}")
    return []


def make_record(query: str, lang: str, category: str) -> dict:
    labels = LABEL_MAP[category]
    return {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "language": lang,
        "query": query,
        "context": [],
        "formal_type": "spoken",
        "intent_type": "factual_query",
        "response_type": "factual",
        "wiki_lookup": False,
        "conv_override": False,
        "qk_entitlement": labels["qk_entitlement"],
        "qk_tvs_estimate": labels["qk_tvs_estimate"],
        "qk_mkr_risk": "low",
        "qk_halfstep_type": "none",
        "qk_reanchor_needed": False,
        "confidence": 0.85,
        "source": "qk_minority_gen_v1",
        "tier": "qk_supplement",
    }


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    dist = {}

    categories = ["abstain", "bounded-only", "high-tvs"]
    languages = ["ja", "en", "zh"]

    for cat in categories:
        for lang in languages:
            key = f"{cat}/{lang}"
            dist[key] = 0
            prompt = PROMPTS[cat][lang]

            for batch in range(BATCHES_PER_COMBO):
                print(f"  [{cat:12s}/{lang}] batch {batch+1}/{BATCHES_PER_COMBO}...",
                      end="", flush=True)
                queries = call_ollama(prompt)
                count = 0
                for q in queries:
                    if len(q) < 5:
                        continue
                    record = make_record(q, lang, cat)
                    with open(OUTPUT, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    total += 1
                dist[key] += count
                print(f" {count} queries")
                time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Total generated: {total}")
    print(f"Output: {OUTPUT}")
    print(f"\nDistribution:")
    for key, count in sorted(dist.items()):
        print(f"  {key:20s}: {count}")


if __name__ == "__main__":
    main()
