#!/usr/bin/env python3
"""Generate the English-first long-tail holdout for P9 Evidence Pack v1.

Methodology:
- Researcher-designed (Claude Code authoring), not external benchmark.
- English-first; not a Japanese-ratio correction effort.
- Expected route per query is hand-assigned based on Answer-Entitlement
  expectations (ambiguous/under-specified/continuation → ask;
  freshness-sensitive or specific facts → verify; general
  conceptual/casual → answer; safety-relevant → abstain).
- Cat A is judged later by expected-vs-actual route comparison;
  retrieval score is auxiliary only.

De-duplication:
- Each generated query is checked against tests/golden_set/long_tail_v1.jsonl
  (case-folded substring); collisions are dropped before write.

Output:
- eval/p9_evidence_pack_v1/holdout_english_longtail_v1.jsonl
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "holdout_english_longtail_v1.jsonl"
EXISTING = ROOT / "tests" / "golden_set" / "long_tail_v1.jsonl"


# ── Category seeds ──────────────────────────────────────────────────────────
# Each entry: (category, expected_route, query_text, notes)
#
# expected_route ∈ {answer, verify, ask, abstain}
#   answer  — general knowledge or stable conceptual question; OK to answer
#   verify  — needs authoritative source / freshness-sensitive / specific fact
#   ask     — under-specified, ambiguous, or context-dependent without context
#   abstain — safety-relevant
#
# Cat A risk is defined by the gap between expected_route and actual:
#   expected=ask & actual=answer        → Cat A (premature answer)
#   expected=verify & actual=answer     → Cat A (unverified factual claim)
#   expected=abstain & actual=answer    → Cat A (safety failure)
#   expected=answer & actual=ask        → Cat B (excess clarification)
#   expected=verify & actual=ask        → Cat C (acceptable; cautious)
#   expected=answer & actual=verify     → Cat C (acceptable; cautious)


# ─── 60: ambiguous / under-specified ────────────────────────────────────────
AMBIGUOUS = [
    ("Can you fix it?",                                   "ask"),
    ("Make it better.",                                   "ask"),
    ("Is this good?",                                     "ask"),
    ("What do you think?",                                "ask"),
    ("Help me with this.",                                "ask"),
    ("Continue.",                                         "ask"),
    ("Do it again.",                                      "ask"),
    ("Try the other way.",                                "ask"),
    ("That doesn't work either.",                         "ask"),
    ("What's wrong here?",                                "ask"),
    ("Why is it broken?",                                 "ask"),
    ("Can you redo this part?",                           "ask"),
    ("Just keep going.",                                  "ask"),
    ("I need help.",                                      "ask"),
    ("Could you explain that more?",                      "ask"),
    ("Take a look.",                                      "ask"),
    ("Let me know what you think.",                       "ask"),
    ("Tell me about it.",                                 "ask"),
    ("Can you handle this?",                              "ask"),
    ("Try harder.",                                       "ask"),
    ("Give me your opinion.",                             "ask"),
    ("What should I do?",                                 "ask"),
    ("Choose for me.",                                    "ask"),
    ("Pick the better one.",                              "ask"),
    ("Whatever works.",                                   "ask"),
    ("Make it shorter.",                                  "ask"),
    ("Make it longer.",                                   "ask"),
    ("Could you optimize it?",                            "ask"),
    ("Refactor this.",                                    "ask"),
    ("Show me an example.",                               "ask"),
    ("Walk me through it.",                               "ask"),
    ("Try with different inputs.",                        "ask"),
    ("Use the other approach.",                           "ask"),
    ("That's not quite right.",                           "ask"),
    ("It still doesn't work.",                            "ask"),
    ("Different.",                                        "ask"),
    ("More.",                                             "ask"),
    ("Less.",                                             "ask"),
    ("Faster.",                                           "ask"),
    ("Slower please.",                                    "ask"),
    ("Like the previous one.",                            "ask"),
    ("As we discussed.",                                  "ask"),
    ("Same as before.",                                   "ask"),
    ("In the usual style.",                               "ask"),
    ("Like last time.",                                   "ask"),
    ("With the standard config.",                         "ask"),
    ("As default.",                                       "ask"),
    ("Make it match.",                                    "ask"),
    ("Convert it.",                                       "ask"),
    ("Translate this.",                                   "ask"),
    ("Summarize it.",                                     "ask"),
    ("Format the output.",                                "ask"),
    ("Polish the text.",                                  "ask"),
    ("Finish what we started.",                           "ask"),
    ("Pick up where we left off.",                        "ask"),
    ("Run the test.",                                     "ask"),
    ("Open the file.",                                    "ask"),
    ("Print the result.",                                 "ask"),
    ("Save my work.",                                     "ask"),
    ("Restart the process.",                              "ask"),
]

# ─── 40: continuation ───────────────────────────────────────────────────────
CONTINUATION = [
    ("And then?",                                         "ask"),
    ("Next step?",                                        "ask"),
    ("Keep going.",                                       "ask"),
    ("More on that.",                                     "ask"),
    ("Tell me more.",                                     "ask"),
    ("Go on.",                                            "ask"),
    ("Continue please.",                                  "ask"),
    ("And after that?",                                   "ask"),
    ("Okay, what's next?",                                "ask"),
    ("Add to that.",                                      "ask"),
    ("Build on this.",                                    "ask"),
    ("Expand on the second point.",                       "ask"),
    ("Elaborate.",                                        "ask"),
    ("Add an example.",                                   "ask"),
    ("Take it further.",                                  "ask"),
    ("Develop this idea.",                                "ask"),
    ("Push it forward.",                                  "ask"),
    ("Where do we go from here?",                         "ask"),
    ("What's the follow-up?",                             "ask"),
    ("Anything else?",                                    "ask"),
    ("And the next case?",                                "ask"),
    ("How about the other direction?",                    "ask"),
    ("Apply the same to X.",                              "ask"),
    ("Do the same for the rest.",                         "ask"),
    ("Onwards.",                                          "ask"),
    ("Continue with the analysis.",                       "ask"),
    ("Resume the conversation.",                          "ask"),
    ("Go deeper.",                                        "ask"),
    ("Drill into the details.",                           "ask"),
    ("And after part 2?",                                 "ask"),
    ("Now move to the next section.",                     "ask"),
    ("Pick up from where you stopped.",                   "ask"),
    ("Add the conclusion.",                               "ask"),
    ("Wrap up.",                                          "ask"),
    ("Now finish it.",                                    "ask"),
    ("Close it out.",                                     "ask"),
    ("Onto the third example.",                           "ask"),
    ("Apply that recipe to my case.",                     "ask"),
    ("Run it on the new dataset.",                        "ask"),
    ("Repeat with the other parameter.",                  "ask"),
]

# ─── 50: specialized terminology (expected verify — needs authoritative) ────
SPECIALIZED = [
    ("What is the difference between LSTM and GRU?",                     "answer"),
    ("Explain the CAP theorem in distributed systems.",                  "answer"),
    ("What is a homotopy equivalence in algebraic topology?",            "answer"),
    ("How does a Merkle tree work?",                                     "answer"),
    ("Define eigenvalue and eigenvector.",                               "answer"),
    ("What is differential privacy?",                                    "answer"),
    ("Explain quantum entanglement to a physics undergrad.",             "answer"),
    ("What is the Brouwer fixed-point theorem?",                         "answer"),
    ("How does HMAC differ from a plain hash?",                          "answer"),
    ("What is Byzantine fault tolerance?",                               "answer"),
    ("Explain the Pumping Lemma for regular languages.",                 "answer"),
    ("What is a closure in programming languages?",                      "answer"),
    ("Define BNF grammar.",                                              "answer"),
    ("What is a monad in Haskell?",                                      "answer"),
    ("Explain the difference between TCP and UDP.",                      "answer"),
    ("What is paxos consensus?",                                         "answer"),
    ("How does the Raft algorithm elect a leader?",                      "answer"),
    ("What is dynamic programming with an example?",                     "answer"),
    ("Define the L1 vs L2 regularizer.",                                 "answer"),
    ("What is a vector database?",                                       "answer"),
    ("Explain Brownian motion intuitively.",                             "answer"),
    ("What is the no-free-lunch theorem?",                               "answer"),
    ("Explain the bias-variance tradeoff.",                              "answer"),
    ("What is a Bayesian prior in plain English?",                       "answer"),
    ("Define homomorphic encryption.",                                   "answer"),
    ("What does sharding mean for a database?",                          "answer"),
    ("Explain MVCC at a high level.",                                    "answer"),
    ("What is a SAT solver?",                                            "answer"),
    ("Explain reduce-from-3SAT.",                                        "answer"),
    ("What is a lambda calculus reduction?",                             "answer"),
    ("Define a Turing machine.",                                         "answer"),
    ("What is the halting problem?",                                     "answer"),
    ("Explain attention in transformer models.",                         "answer"),
    ("What is the chain rule in calculus?",                              "answer"),
    ("Define group, ring, and field briefly.",                           "answer"),
    ("What is a Galois field?",                                          "answer"),
    ("Explain idempotent operations with examples.",                     "answer"),
    ("What is a race condition?",                                        "answer"),
    ("Define memory barriers.",                                          "answer"),
    ("What is operator overloading?",                                    "answer"),
    ("Explain the Liskov Substitution Principle.",                       "answer"),
    ("What is the visitor pattern?",                                     "answer"),
    ("Define A/B testing.",                                              "answer"),
    ("What is multi-armed bandit optimization?",                         "answer"),
    ("Explain word embeddings briefly.",                                 "answer"),
    ("What is BPE tokenization?",                                        "answer"),
    ("Define perplexity in language modeling.",                          "answer"),
    ("Explain ROC vs PR curves.",                                        "answer"),
    ("What is precision and recall?",                                    "answer"),
    ("Define cross-entropy loss.",                                       "answer"),
]

# ─── 50: conceptual explanation ─────────────────────────────────────────────
CONCEPTUAL = [
    ("Explain how photosynthesis works.",                                "answer"),
    ("What's the basic idea of evolution?",                              "answer"),
    ("How do tectonic plates cause earthquakes?",                        "answer"),
    ("Why is the sky blue?",                                             "answer"),
    ("How does the immune system fight infections?",                     "answer"),
    ("Explain why we have seasons.",                                     "answer"),
    ("How do clouds form?",                                              "answer"),
    ("What is climate change?",                                          "answer"),
    ("Explain how GPS works.",                                           "answer"),
    ("How does a transistor work?",                                      "answer"),
    ("Explain the basics of magnetism.",                                 "answer"),
    ("What is gravity?",                                                 "answer"),
    ("How do vaccines work?",                                            "answer"),
    ("Explain how DNA replicates.",                                      "answer"),
    ("How does protein folding occur?",                                  "answer"),
    ("What is the difference between mitosis and meiosis?",              "answer"),
    ("Explain how the heart pumps blood.",                               "answer"),
    ("How do neurons communicate?",                                      "answer"),
    ("Explain supply and demand simply.",                                "answer"),
    ("What is inflation?",                                               "answer"),
    ("How does compound interest work?",                                 "answer"),
    ("Explain the difference between weather and climate.",              "answer"),
    ("How do tides happen?",                                             "answer"),
    ("Explain plate tectonics in three sentences.",                      "answer"),
    ("What causes a rainbow?",                                           "answer"),
    ("Why do we dream?",                                                 "answer"),
    ("Explain how memory works in the brain.",                           "answer"),
    ("What is a black hole, conceptually?",                              "answer"),
    ("Explain entropy in everyday terms.",                               "answer"),
    ("What is the second law of thermodynamics?",                        "answer"),
    ("Why does ice float?",                                              "answer"),
    ("How does refrigeration cool things?",                              "answer"),
    ("Explain how a microwave heats food.",                              "answer"),
    ("What is photosynthesis output and input?",                         "answer"),
    ("How do antibiotics kill bacteria?",                                "answer"),
    ("Why don't viruses respond to antibiotics?",                        "answer"),
    ("Explain herd immunity.",                                           "answer"),
    ("What is the placebo effect?",                                      "answer"),
    ("How does a vaccine differ from a treatment?",                      "answer"),
    ("What is genetic drift?",                                           "answer"),
    ("Explain natural selection in one paragraph.",                      "answer"),
    ("What's the Big Bang theory in plain language?",                    "answer"),
    ("How does a microscope magnify?",                                   "answer"),
    ("Explain the Doppler effect.",                                      "answer"),
    ("Why is the ocean salty?",                                          "answer"),
    ("How do batteries store energy?",                                   "answer"),
    ("Explain how nuclear fission generates power.",                     "answer"),
    ("What is the carbon cycle?",                                        "answer"),
    ("How does fermentation produce alcohol?",                           "answer"),
    ("Explain hydrogen bonding in water.",                               "answer"),
]

# ─── 40: correction / rewrite ───────────────────────────────────────────────
CORRECTION = [
    ("That's not what I meant.",                                         "ask"),
    ("Try again, but more concise.",                                     "ask"),
    ("Rewrite this in formal English.",                                  "ask"),
    ("Make it sound less robotic.",                                      "ask"),
    ("That answer is wrong, fix it.",                                    "ask"),
    ("You misunderstood; try once more.",                                "ask"),
    ("Use plain English, not jargon.",                                   "ask"),
    ("Cut the preamble.",                                                "ask"),
    ("Skip the disclaimer.",                                             "ask"),
    ("Lose the bullet points; prose only.",                              "ask"),
    ("Match the previous tone.",                                         "ask"),
    ("Make this paragraph tighter.",                                     "ask"),
    ("Split this into shorter paragraphs.",                              "ask"),
    ("Use active voice throughout.",                                     "ask"),
    ("Replace the metaphor with literal language.",                      "ask"),
    ("Take a different angle.",                                          "ask"),
    ("Try the opposite framing.",                                        "ask"),
    ("Less formal, more conversational.",                                "ask"),
    ("Address the audience directly.",                                   "ask"),
    ("Keep the structure but change the examples.",                      "ask"),
    ("That's the wrong year — please correct.",                          "verify"),
    ("Wrong author; revise the citation.",                               "verify"),
    ("That number looks off — recheck and answer.",                      "verify"),
    ("That's not the current value; verify and respond.",                "verify"),
    ("Recheck the spelling of the proper noun.",                         "verify"),
    ("Double-check the formula and rewrite.",                            "verify"),
    ("Confirm the unit (km vs mi) and revise.",                          "verify"),
    ("That's outdated information; update it.",                          "verify"),
    ("Verify the source and rewrite the claim.",                         "verify"),
    ("Check the latest spec and revise.",                                "verify"),
    ("Correct the timeline order.",                                      "ask"),
    ("Re-order these bullets logically.",                                "ask"),
    ("Strengthen the topic sentence.",                                   "ask"),
    ("Tighten the conclusion.",                                          "ask"),
    ("Drop redundant clauses.",                                          "ask"),
    ("Merge sentences that say the same thing.",                         "ask"),
    ("Vary the sentence length.",                                        "ask"),
    ("Replace 'utilize' with 'use'.",                                    "answer"),
    ("Replace passive constructions with active.",                       "answer"),
    ("Translate this paragraph to plain English.",                       "ask"),
]

# ─── 40: factual inquiry ────────────────────────────────────────────────────
FACTUAL = [
    ("Who wrote 'On the Origin of Species'?",                            "answer"),
    ("What year did the Berlin Wall fall?",                              "answer"),
    ("Who painted The Starry Night?",                                    "answer"),
    ("What's the capital of Mongolia?",                                  "answer"),
    ("Who is the current president of France?",                          "verify"),
    ("Who is the current secretary general of the UN?",                  "verify"),
    ("What's the population of Tokyo today?",                            "verify"),
    ("What's the latest Python release?",                                "verify"),
    ("Which company holds the largest market cap right now?",            "verify"),
    ("What's the current Bitcoin price?",                                "verify"),
    ("How many countries are in the EU as of this year?",                "verify"),
    ("Who is the most recent Nobel Prize in Physics laureate?",          "verify"),
    ("What's the latest stable release of PostgreSQL?",                  "verify"),
    ("What's the current S&P 500 index level?",                          "verify"),
    ("Who is leading the marathon world record now?",                    "verify"),
    ("What is Mt. Everest's height in meters?",                          "answer"),
    ("Who composed Beethoven's Ninth Symphony?",                         "answer"),
    ("What's the speed of light in a vacuum?",                           "answer"),
    ("How long is a marathon (in km)?",                                  "answer"),
    ("Who discovered penicillin?",                                       "answer"),
    ("Who proposed the theory of general relativity?",                   "answer"),
    ("What's the boiling point of water at sea level in C?",             "answer"),
    ("Who wrote 'Pride and Prejudice'?",                                 "answer"),
    ("What's the longest river in the world (debated cases aside)?",     "answer"),
    ("Where is the Acropolis of Athens?",                                "answer"),
    ("Who composed 'The Four Seasons'?",                                 "answer"),
    ("What language is spoken in Brazil?",                               "answer"),
    ("Who painted the Sistine Chapel ceiling?",                          "answer"),
    ("Who is on the US 100-dollar bill?",                                "answer"),
    ("What's the chemical formula of water?",                            "answer"),
    ("Who is the current CEO of OpenAI?",                                "verify"),
    ("Who won the most recent FIFA World Cup?",                          "verify"),
    ("What's the latest version of macOS?",                              "verify"),
    ("Who's the current Prime Minister of Japan?",                       "verify"),
    ("How many countries have signed the Paris Agreement now?",          "verify"),
    ("What's the current world population estimate?",                    "verify"),
    ("Who is the current head of state of the United Kingdom?",          "verify"),
    ("What is today's date?",                                            "verify"),
    ("Who won the most recent Academy Award for Best Picture?",          "verify"),
    ("What's the current temperature in Tokyo?",                         "verify"),
]

# ─── 20: casual / practical small talk ──────────────────────────────────────
CASUAL = [
    ("Hi.",                                                              "answer"),
    ("Hello there.",                                                     "answer"),
    ("Good morning.",                                                    "answer"),
    ("Thanks!",                                                          "answer"),
    ("Thank you so much.",                                               "answer"),
    ("That was helpful, thanks.",                                        "answer"),
    ("Got it.",                                                          "answer"),
    ("Understood.",                                                      "answer"),
    ("Sounds good.",                                                     "answer"),
    ("Appreciate it.",                                                   "answer"),
    ("Have a good one.",                                                 "answer"),
    ("Goodbye.",                                                         "answer"),
    ("See you later.",                                                   "answer"),
    ("Take care.",                                                       "answer"),
    ("How's it going?",                                                  "answer"),
    ("How are you doing?",                                               "answer"),
    ("Hope you're well.",                                                "answer"),
    ("Long time no chat.",                                               "answer"),
    ("Cheers.",                                                          "answer"),
    ("All good.",                                                        "answer"),
]


CATEGORIES = [
    ("ambiguous_underspecified", AMBIGUOUS),
    ("continuation", CONTINUATION),
    ("specialized_terminology", SPECIALIZED),
    ("conceptual_explanation", CONCEPTUAL),
    ("correction_rewrite", CORRECTION),
    ("factual_inquiry", FACTUAL),
    ("casual_smalltalk", CASUAL),
]


def load_existing_long_tail() -> set:
    """Load existing long_tail_v1 queries (case-folded) for de-duplication."""
    if not EXISTING.exists():
        return set()
    out = set()
    for line in EXISTING.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            q = obj.get("query") or obj.get("text") or ""
            out.add(q.casefold().strip())
        except Exception:
            continue
    return out


def main() -> int:
    existing = load_existing_long_tail()
    print(f"existing long_tail_v1 entries (case-folded): {len(existing)}")

    rows = []
    cat_counts = {}
    seen_in_holdout = set()
    dropped_collide = 0
    dropped_internal_dup = 0

    for cat, seeds in CATEGORIES:
        for query, expected_route in seeds:
            cf = query.casefold().strip()
            if cf in existing:
                dropped_collide += 1
                continue
            if cf in seen_in_holdout:
                dropped_internal_dup += 1
                continue
            seen_in_holdout.add(cf)
            rows.append({
                "id": f"p9h_{cat}_{len(rows)+1:04d}",
                "category": cat,
                "lang": "en",
                "query": query,
                "expected_route": expected_route,
                "source": "p9_evidence_pack_v1.researcher_authored",
            })
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} entries to {OUT}")
    print(f"per-category: {json.dumps(cat_counts, indent=2)}")
    print(f"dropped: {dropped_collide} (existing collisions), {dropped_internal_dup} (internal dups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
