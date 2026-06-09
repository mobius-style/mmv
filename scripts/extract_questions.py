#!/usr/bin/env python3
"""
extract_questions.py — Literary question extraction (parallel task)

Extracts question candidates from public domain texts.
Uses qwen3.5:4b (local) for yes/no question classification.

Output: data/raw/questions_literary.jsonl

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

JA_PATTERNS = [
    re.compile(r"[？?]"),
    re.compile(r"[なぜなんでどうしてどこいつだれなにどう].{0,30}[かのだろ]"),
    re.compile(r".{0,30}[かしらかなのかだろうではないか]$"),
]

EN_PATTERNS = [
    re.compile(r"\?"),
    re.compile(r"^(What|Who|Where|When|Why|How|Is|Are|Was|Were|Do|Does|Did|Can|Could|Would|Should)\s"),
]

ZH_PATTERNS = [
    re.compile(r"[？?]"),
    re.compile(r"[吗呢啊吧]$"),
    re.compile(r"^(为什么|怎么|什么|哪里|谁|何时)"),
]


def is_question(text: str, language: str) -> bool:
    patterns = {"ja": JA_PATTERNS, "en": EN_PATTERNS, "zh": ZH_PATTERNS}
    for p in patterns.get(language, EN_PATTERNS):
        if p.search(text):
            return True
    return False


def extract_from_file(path: str, language: str) -> list[str]:
    """Extract question sentences from a text file."""
    questions = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if 10 < len(line) < 200 and is_question(line, language):
                    questions.append(line)
    except Exception:
        pass
    return questions


if __name__ == "__main__":
    print("extract_questions.py — Ready for Phase 2")
    print("Usage: python scripts/extract_questions.py --input <text_file> --lang ja")
