#!/usr/bin/env python3
"""
live_verify_test.py — End-to-end verify route smoke test with Brave Search.

Run from MOBIUS_MMV directory with venv313 activated:
    python live_verify_test.py

Requires:
    .env file with BRAVE_API_KEY=...
"""
import os
import sys

# Load .env manually (no python-dotenv dependency)
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(__file__))

from src.adapters.brave_search_adapter import BraveSearchAdapter
from src.retrieval.web_result_normalizer import normalize_search_response
from src.adjudication.evidence_adjudicator import adjudicate_evidence
from src.compose.verify_synthesizer import synthesize_verify_response

QUERIES = [
    # Demo A: freshness-sensitive fact
    ("Who is the current prime minister of Japan?", "policy"),
    # Demo B: under-specified → should ask, not search (routing test)
    ("What are the latest changes?", "general"),
    # Demo C: policy explanation
    ("What is Japan's current consumption tax rate?", "policy"),
]

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

for query, preset in QUERIES:
    separator(f"QUERY: {query}")

    adapter = BraveSearchAdapter()
    raw = adapter.search(query, max_results=5, freshness_hint="recent", preset=preset)

    print(f"Provider : {raw.provider}")
    print(f"Success  : {raw.success}")
    if not raw.success:
        print(f"Error    : {raw.error_message}")
        continue

    print(f"Results  : {len(raw.results)}")

    normalized = normalize_search_response(raw)
    print(f"After norm: {len(normalized.results)} results")

    adjudicated = adjudicate_evidence(normalized, query, preset=preset)
    print(f"\nAdjudication:")
    for r in adjudicated.rationale:
        print(f"  {r}")

    synth = synthesize_verify_response(
        query=query,
        adjudicated=adjudicated,
        active_language="en",
        preset=preset,
        adapter=None,  # no LLM in smoke test
    )

    print(f"\nVerify outcome : {synth['verify_outcome']}")
    print(f"Response       : {synth['response_text']}")
    print(f"Sources        :")
    for s in synth["sources"][:3]:
        print(f"  [{s['source_name']}] {s['url'][:80]}")

print("\n" + "="*60)
print("  Smoke test complete")
print("="*60)
