#!/usr/bin/env python3
"""
test_wallball_compare.py — Wall-ball 4-pattern comparison test

Pattern A: qwen3.5:4b x 3 languages (speed priority)
Pattern B: qwen3.5:9b x 3 languages (quality priority)
Pattern C: qwen3.5:4b(ja/zh) + phi4-mini(en) (cross-arch diversity)
Pattern D: qwen3.5:4b(ja/zh) + qwen3.5:9b(en) (same-family size diversity)

Author : Taiko Toeda / MOBIUS LLC
"""
import asyncio
import aiohttp
import time
import json
import os
from collections import Counter

OLLAMA = "http://localhost:11434/api/generate"

TEST_PROMPTS = {
    "ja": [
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
    "en": [
        "History and culture",
        "Daily conversation",
        "Science and technology",
        "Word games",
        "Translation requests",
        "Philosophy and ethics",
        "Mathematics and logic",
        "Clarification and correction",
        "Geography and travel",
        "Music and art",
    ],
    "zh": [
        "Chinese history and culture",
        "Daily conversation",
        "Science and technology",
        "Translation requests",
        "Philosophical questions",
        "Mathematics and logic",
        "Geography",
        "Literature",
        "Health and medicine",
        "Education",
    ],
}

LANG_LABEL = {"ja": "Japanese", "en": "English", "zh": "Chinese"}


async def generate(session, model, topic, lang):
    start = time.time()
    prompt = (
        f"Generate a single natural question in {LANG_LABEL[lang]} "
        f"about: {topic}\n"
        f"Output the question only, no explanation."
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.8, "num_predict": 80},
    }
    if "qwen" in model.lower():
        payload["think"] = False

    try:
        async with session.post(
            OLLAMA, json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            data = await resp.json()
            elapsed = time.time() - start
            query = data.get("response", "").strip()
            for prefix in ["Question:", "Q:", "Here"]:
                if query.startswith(prefix):
                    query = query.split("\n")[0]
                    if query.startswith(prefix):
                        query = query[len(prefix):].strip()
            return {"query": query, "latency": elapsed, "model": model, "lang": lang, "topic": topic}
    except Exception as e:
        return {"query": "", "latency": time.time() - start, "model": model, "lang": lang, "error": str(e)}


def ngram_diversity(texts, n=3):
    if not texts:
        return 0.0
    all_ngrams = []
    for t in texts:
        if len(t) >= n:
            all_ngrams.extend(t[i:i+n] for i in range(len(t) - n + 1))
    if not all_ngrams:
        return 0.0
    counter = Counter(all_ngrams)
    unique = sum(1 for v in counter.values() if v == 1)
    return unique / len(all_ngrams)


async def run_pattern(name, model_map, prompts_per_lang=10):
    print(f"\n{'='*60}")
    print(f"Pattern: {name}")
    for lang, m in model_map.items():
        print(f"  {lang}: {m}")
    print("=" * 60)

    results = []
    errors = 0
    t0 = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for lang, topics in TEST_PROMPTS.items():
            model = model_map[lang]
            for topic in topics[:prompts_per_lang]:
                tasks.append(generate(session, model, topic, lang))
        outputs = await asyncio.gather(*tasks)

    total_time = time.time() - t0

    for out in outputs:
        if out.get("error") or not out.get("query"):
            errors += 1
        else:
            results.append(out)
            print(f"  [{out['lang']}] {out['latency']:.1f}s | {out['query'][:70]}")

    diversity = {}
    for lang in ["ja", "en", "zh"]:
        lang_q = [r["query"] for r in results if r["lang"] == lang and r["query"]]
        diversity[lang] = ngram_diversity(lang_q)
        avg_lat = sum(r["latency"] for r in results if r["lang"] == lang) / max(len(lang_q), 1)
        print(f"  [{lang}] diversity={diversity[lang]:.3f} avg_lat={avg_lat:.1f}s model={model_map[lang]}")

    avg_latency = sum(r["latency"] for r in results) / max(len(results), 1)
    print(f"\n  Total: {total_time:.1f}s | Avg: {avg_latency:.1f}s | OK: {len(results)} | Err: {errors}")

    return {
        "pattern": name, "model_map": model_map, "results": results,
        "total_time": total_time, "avg_latency": avg_latency,
        "diversity": diversity, "count": len(results), "errors": errors,
    }


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:11434/api/tags") as resp:
            data = await resp.json()
    available = [m["name"] for m in data.get("models", [])]
    print("Available models:", [m for m in available if "qwen" in m or "phi4" in m])

    has_9b  = any("qwen3.5:9b" in m for m in available)
    has_phi = any("phi4-mini" in m for m in available)
    phi_model = "phi4-mini:latest" if has_phi else None

    patterns = []

    # A: qwen3.5:4b x 3
    patterns.append(await run_pattern(
        "A: qwen3.5:4b x3 (speed)",
        {"ja": "qwen3.5:4b", "en": "qwen3.5:4b", "zh": "qwen3.5:4b"},
    ))

    # B: qwen3.5:9b x 3
    if has_9b:
        patterns.append(await run_pattern(
            "B: qwen3.5:9b x3 (quality)",
            {"ja": "qwen3.5:9b", "en": "qwen3.5:9b", "zh": "qwen3.5:9b"},
        ))

    # C: 4b(ja/zh) + phi4-mini(en)
    if has_phi:
        patterns.append(await run_pattern(
            f"C: 4b(ja/zh)+phi4-mini(en) (cross-arch)",
            {"ja": "qwen3.5:4b", "en": phi_model, "zh": "qwen3.5:4b"},
        ))

    # D: 4b(ja/zh) + 9b(en)
    if has_9b:
        patterns.append(await run_pattern(
            "D: 4b(ja/zh)+9b(en) (size diversity)",
            {"ja": "qwen3.5:4b", "en": "qwen3.5:9b", "zh": "qwen3.5:4b"},
        ))

    # Summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Pattern':<42} {'Total':>6} {'Avg':>5} {'ja':>6} {'en':>6} {'zh':>6} {'Err':>4}")
    print("-" * 70)
    for p in patterns:
        d = p["diversity"]
        print(f"{p['pattern'][:42]:<42} {p['total_time']:>5.1f}s {p['avg_latency']:>4.1f}s "
              f"{d.get('ja',0):>6.3f} {d.get('en',0):>6.3f} {d.get('zh',0):>6.3f} {p['errors']:>4}")

    print("\nEfficiency score (avg_diversity / avg_latency):")
    for p in patterns:
        avg_div = sum(p["diversity"].values()) / 3
        score = avg_div / max(p["avg_latency"], 0.1)
        p["efficiency_score"] = score
        p["avg_diversity"] = avg_div
        print(f"  {p['pattern'][:42]:<42} score={score:.4f} (div={avg_div:.3f} / {p['avg_latency']:.1f}s)")

    best = max(patterns, key=lambda p: p["efficiency_score"])
    print(f"\n  Recommended: {best['pattern']}")

    # ISM check
    print("\n" + "=" * 70)
    print("ISM Index Status")
    chunks_path = "data/raf/ism_chunks.jsonl"
    if os.path.exists(chunks_path):
        with open(chunks_path) as f:
            first = json.loads(f.readline())
        print(f"  embedding_model: intfloat/multilingual-e5-large (inferred from build script)")
        print(f"  Note: multilingual ME5 scoring enabled.")

    # Tier-3 adoption
    raw_path = "data/raf/wall_ball_raw.jsonl"
    teacher_path = "data/raf/teacher_data_raw.jsonl"
    if os.path.exists(raw_path) and os.path.exists(teacher_path):
        with open(raw_path) as f:
            raw_count = sum(1 for _ in f)
        with open(teacher_path) as f:
            teacher_count = sum(1 for _ in f)
        rate = teacher_count / max(raw_count, 1) * 100
        print(f"\n  Tier-3 adoption: {teacher_count}/{raw_count} = {rate:.1f}%")

    # Save
    os.makedirs("data/raf", exist_ok=True)
    save = [{
        "pattern": p["pattern"], "model_map": p["model_map"],
        "total_time": p["total_time"], "avg_latency": p["avg_latency"],
        "diversity": p["diversity"], "avg_diversity": p.get("avg_diversity", 0),
        "efficiency_score": p.get("efficiency_score", 0),
        "count": p["count"], "errors": p["errors"],
        "samples": {lang: [r["query"] for r in p["results"] if r["lang"] == lang][:3] for lang in ["ja", "en", "zh"]},
    } for p in patterns]
    with open("data/raf/wallball_test_results.json", "w", encoding="utf-8") as f:
        json.dump(save, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: data/raf/wallball_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
