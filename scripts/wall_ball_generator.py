#!/usr/bin/env python3
"""
wall_ball_generator.py — ISM+QK corpus generation (GPU-split capable)

GPU-split usage:
  Terminal 1 (GPU0): --turns 100000 --langs ja,zh
  Terminal 2 (GPU1): --turns 100000 --langs en --ollama-port 11435 \
                     --output data/raf/wall_ball_raw_gpu1.jsonl

Auto-stops when novelty_rate < 0.05 for 3 consecutive cycles.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
import fcntl
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.adapters.raf.tier_evaluator import TierEvaluator, JUDGE_SAMPLE_RATE

# Worker config: language -> (ollama_url, model)
WORKERS = {
    "ja": ("http://localhost:11434/api/generate", "qwen3.5:4b"),
    "en": ("http://localhost:11435/api/generate", "qwen3.5:4b"),
    "zh": ("http://localhost:11434/api/generate", "qwen3.5:4b"),
}

RAW_LOG_PATH = ROOT / "data" / "raf" / "wall_ball_raw.jsonl"
TEACHER_PATH = ROOT / "data" / "raf" / "teacher_data_raw.jsonl"

# Convergence detection
CONVERGENCE_BATCH   = 100   # Check every N generated entries
CONVERGENCE_THRESH  = 0.05  # novelty_rate below this = converging
CONVERGENCE_CYCLES  = 3     # Consecutive cycles needed to stop

LANGUAGE_TOPICS = {
    "ja": {
        "weight": 0.50,
        "topics": [
            "Japanese history and culture",
            "Daily conversation and greetings",
            "Science and technology",
            "Shiritori and word games",
            "Translation requests",
            "Cooking and recipes",
            "Philosophical questions",
            "Mathematics and logic",
            "Sports and health",
            "Correction and clarification",
        ],
    },
    "en": {
        "weight": 0.30,
        "topics": [
            "History and culture",
            "Daily conversation",
            "Science and technology",
            "Word games",
            "Translation requests",
            "Philosophy and ethics",
            "Mathematics and logic",
            "Clarification and correction",
        ],
    },
    "zh": {
        "weight": 0.20,
        "topics": [
            "Chinese history and culture",
            "Daily conversation",
            "Science and technology",
            "Translation requests",
            "Philosophical questions",
            "Mathematics and logic",
        ],
    },
}

LANG_PROMPTS = {
    "ja": "Generate a natural Japanese question about the topic '{topic}'. Output ONLY the question, no explanation.",
    "en": "Generate a natural English question about the topic '{topic}'. Output ONLY the question, no explanation.",
    "zh": "Generate a natural Chinese question about the topic '{topic}'. Output ONLY the question, no explanation.",
}


def _append_jsonl(path: Path, entry: dict) -> None:
    """Append with file lock to prevent corruption from parallel processes."""
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line)
        fcntl.flock(f, fcntl.LOCK_UN)


def _check_novelty() -> float:
    """
    Calculate novelty as distribution shift between recent and older batches.
    Uses n-gram diversity on query text instead of pattern counting,
    because intent_type patterns saturate quickly (~19 types).
    Returns 0.0 (identical) to 1.0 (completely novel).
    """
    if not TEACHER_PATH.exists():
        return 1.0
    lines = []
    with open(TEACHER_PATH, encoding="utf-8") as f:
        for line in f:
            lines.append(line.strip())
    total = len(lines)
    if total < CONVERGENCE_BATCH * 2:
        return 1.0

    # Compare last batch vs previous batch
    recent_lines = lines[-CONVERGENCE_BATCH:]
    older_lines  = lines[-(CONVERGENCE_BATCH * 2):-CONVERGENCE_BATCH]

    def _extract_ngrams(text_lines, n=4):
        ngrams = set()
        for line in text_lines:
            try:
                q = json.loads(line).get("query", "")
                for i in range(len(q) - n + 1):
                    ngrams.add(q[i:i+n])
            except Exception:
                pass
        return ngrams

    recent_ng = _extract_ngrams(recent_lines)
    older_ng  = _extract_ngrams(older_lines)

    if not recent_ng:
        return 1.0
    new_ngrams = recent_ng - older_ng
    novelty = len(new_ngrams) / len(recent_ng)

    print(f"  [NOVELTY] total={total} recent_ng={len(recent_ng)} "
          f"older_ng={len(older_ng)} new={len(new_ngrams)} rate={novelty:.3f}")
    return novelty


async def query_ollama_async(session, url, model, prompt, temperature=0.8):
    import aiohttp
    t0 = time.time()
    try:
        async with session.post(
            url,
            json={"model": model, "prompt": prompt, "stream": False,
                  "think": False,
                  "options": {"temperature": temperature, "num_predict": 100}},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json()
            return data.get("response", "").strip(), (time.time() - t0) * 1000
    except Exception as e:
        return f"[ERROR] {e}", 0.0


async def generate_one(session, language, topic, evaluator, groq_key,
                        recent, session_id, probe, verbose, idx, total):
    url, model = WORKERS[language]

    ctx_prompt = (
        f"You are having a conversation in {language} about '{topic}'. "
        f"Generate one short statement. Output ONLY the statement in {language}."
    )
    ctx_text, _ = await query_ollama_async(session, url, model, ctx_prompt, 0.9)
    context_turns = [{"role": "assistant", "content": ctx_text}]

    prompt = LANG_PROMPTS[language].format(topic=topic)
    query, latency = await query_ollama_async(session, url, model, prompt)

    if not query or query.startswith("[ERROR"):
        return None

    if not evaluator.lint(query, recent):
        return None

    # Tier-2 mirror
    import requests
    try:
        r = requests.post(url, json={
            "model": model, "stream": False, "think": False,
            "prompt": f"Rate whether this is a natural question (0.0 to 1.0).\nQuery: {query}\nOutput only a number:",
            "options": {"num_predict": 10, "temperature": 0.0}
        }, timeout=15)
        t2_score = 0.5
        for tok in r.json().get("response", "0.5").strip().split():
            try:
                t2_score = min(1.0, max(0.0, float(tok)))
                break
            except ValueError:
                continue
    except Exception:
        t2_score = 0.5

    # Tier-3
    t3_label = None
    t3_raw = ""
    if (random.random() < JUDGE_SAMPLE_RATE or probe) and groq_key:
        t3_label = evaluator.judge(query, ctx_text, language, groq_key)
        t3_raw = json.dumps(t3_label, ensure_ascii=False) if t3_label else ""

    tier = 3 if t3_label else (2 if t2_score >= 0.45 else 1)
    worker_port = 11434 if "11434" in url else 11435

    raw_entry = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "language": language, "topic": topic,
        "context_turns": context_turns, "query": query,
        "worker_port": worker_port,
        "tier1_pass": True, "tier2_score": round(t2_score, 3),
        "tier2_raw": str(t2_score),
        "tier3_label": t3_label or {}, "tier3_raw": t3_raw,
        "groq_model": "openai/gpt-oss-120b" if t3_label else "",
        "groq_latency_ms": 0.0, "groq_tokens": 0,
    }
    _append_jsonl(RAW_LOG_PATH, raw_entry)

    if t3_label:
        teacher_entry = {
            "id": raw_entry["id"], "created_at": raw_entry["created_at"],
            "language": language, "query": query, "context": ctx_text,
            "formal_type": t3_label.get("formal_type", "other"),
            "intent_type": t3_label.get("intent_type", "factual_query"),
            "response_type": "direct_answer",
            "wiki_lookup": t3_label.get("wiki_lookup", True),
            "conv_override": t3_label.get("conv_override", False),
            "qk_entitlement": t3_label.get("qk_entitlement", "answerable"),
            "qk_tvs_estimate": t3_label.get("qk_tvs_estimate", "low"),
            "qk_mkr_risk": t3_label.get("qk_mkr_risk", "low"),
            "qk_halfstep_type": t3_label.get("qk_halfstep_type", "none"),
            "qk_reanchor_needed": False,
            "confidence": t3_label.get("confidence", 0.5),
            "source": "groq_judge", "tier": tier,
        }
        _append_jsonl(TEACHER_PATH, teacher_entry)

    recent.append(query)
    if len(recent) > 50:
        recent.pop(0)

    if verbose:
        intent = t3_label.get("intent_type", "?") if t3_label else "?"
        qk = t3_label.get("qk_entitlement", "?") if t3_label else "?"
        print(f"  [{idx+1}/{total}] {language} T{tier} W{worker_port} "
              f"{intent:20s} {qk:10s} {query[:50]}")

    return raw_entry


async def run_generation_async(n_turns, groq_key, probe, verbose):
    import aiohttp
    evaluator = TierEvaluator()
    recent = []
    session_id = str(uuid.uuid4())[:8]

    active_langs = set(WORKERS.keys())
    # Re-normalize weights for selected languages
    raw_weights = {lang: LANGUAGE_TOPICS[lang]["weight"]
                   for lang in LANGUAGE_TOPICS if lang in active_langs}
    weight_sum = sum(raw_weights.values()) or 1.0
    norm_weights = {lang: w / weight_sum for lang, w in raw_weights.items()}

    tasks_spec = []
    for lang, weight in norm_weights.items():
        count = max(1, int(n_turns * weight))
        topics = LANGUAGE_TOPICS[lang]["topics"]
        for _ in range(count):
            tasks_spec.append((lang, random.choice(topics)))
    random.shuffle(tasks_spec)
    tasks_spec = tasks_spec[:n_turns]

    RAW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated = 0
    total = len(tasks_spec)
    converge_streak = 0

    BATCH = 6
    async with aiohttp.ClientSession() as session:
        for batch_start in range(0, total, BATCH):
            batch = tasks_spec[batch_start:batch_start + BATCH]
            coros = [
                generate_one(session, lang, topic, evaluator, groq_key,
                             recent, session_id, probe, verbose,
                             batch_start + j, total)
                for j, (lang, topic) in enumerate(batch)
            ]
            results = await asyncio.gather(*coros, return_exceptions=True)
            generated += sum(1 for r in results if r and not isinstance(r, Exception))

            # Convergence check every CONVERGENCE_BATCH entries
            if generated > 0 and generated % CONVERGENCE_BATCH < BATCH:
                novelty = _check_novelty()
                if novelty < CONVERGENCE_THRESH:
                    converge_streak += 1
                    print(f"  [CONVERGE] novelty_rate={novelty:.3f} "
                          f"streak={converge_streak}/{CONVERGENCE_CYCLES}")
                    if converge_streak >= CONVERGENCE_CYCLES:
                        print(f"  [CONVERGED] novelty_rate={novelty:.3f} "
                              f"after {generated} entries — stopping")
                        return generated
                else:
                    converge_streak = 0

    return generated


def run_generation(n_turns, groq_key, probe=False, verbose=True):
    return asyncio.run(run_generation_async(n_turns, groq_key, probe, verbose))


def main():
    global WORKERS, RAW_LOG_PATH

    parser = argparse.ArgumentParser(description="ISM+QK corpus generator (GPU-split)")
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--groq-key", default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--langs", default=None,
                        help="Comma-separated languages (e.g. ja,zh or en)")
    parser.add_argument("--output", default=None,
                        help="Output JSONL path")
    parser.add_argument("--ollama-port", type=int, default=None,
                        help="Override Ollama port (e.g. 11435)")
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    groq_key = args.groq_key or os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        print("[ERROR] GROQ_API_KEY not set. Use --groq-key or .env")
        sys.exit(1)

    if args.ollama_port:
        url = f"http://localhost:{args.ollama_port}/api/generate"
        WORKERS = {lang: (url, "qwen3.5:4b") for lang in WORKERS}

    if args.langs:
        selected = [l.strip() for l in args.langs.split(",")]
        WORKERS = {k: v for k, v in WORKERS.items() if k in selected}

    if args.output:
        RAW_LOG_PATH = Path(args.output)

    n_turns = 30 if args.probe else args.turns
    print(f"=== Wall-Ball Generator (GPU-split) ===")
    print(f"Mode:       {'PROBE' if args.probe else 'FULL'}")
    print(f"Turns:      {n_turns} (max, auto-stops on convergence)")
    print(f"Langs:      {list(WORKERS.keys())}")
    print(f"Workers:    {WORKERS}")
    print(f"Output:     {RAW_LOG_PATH}")
    print(f"Teacher:    {TEACHER_PATH}")
    print(f"Converge:   novelty<{CONVERGENCE_THRESH} x{CONVERGENCE_CYCLES} cycles")

    n = run_generation(n_turns, groq_key, probe=args.probe, verbose=not args.quiet)
    print(f"\nGenerated: {n} entries")
    print(f"Raw log:   {RAW_LOG_PATH}")
    print(f"Teacher:   {TEACHER_PATH}")


if __name__ == "__main__":
    main()
