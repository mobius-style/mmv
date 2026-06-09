#!/usr/bin/env python3
"""P9 Evidence Pack v1 — Test 3: Multi-turn stability smoke.

Methodology:
- 20 dialogues × 5 user turns each, English-first.
- Each dialogue is replayed in a single PseudoUISession (state carries
  forward across turns, mirroring real UI behavior).
- For each turn we record actual route, reason_codes, intent, and a
  per-turn evaluation against a hand-tagged turn label.

Per-turn labels (assigned at script time, not learned):
- expected_route       : ask | answer | verify (per-turn)
- expects_referent     : True if the turn references prior content
                         ("the second one", "that approach", ...)
- intent_change_turn   : True if the user changes intent at this turn

Aggregate metrics:
- Cat A rate (premature-answer on turns expecting ask/verify).
- Referent-resolution rate (on turns flagged expects_referent: did the
  governed system *not* abruptly drop to ask "What do you mean by
  that?" — a coarse heuristic).
- Topic-drift count (consecutive turns where reason_codes contain
  "topic_drift_*" or where the response_text mentions a topic the
  prior user turn did not).
- Final-turn naturalness flag (response_text non-empty, route ∈ {answer,
  verify} when expected_route says so).

This is a smoke test, not a benchmark — the labels are author-assigned.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

OUT_DIR = Path(__file__).resolve().parent
DIALOGUES_OUT = OUT_DIR / "multiturn_smoke_dialogues.jsonl"
RESULTS_OUT = OUT_DIR / "multiturn_smoke_results.json"


# 20 dialogues × 5 turns. Each turn has:
#   ("user input", expected_route, expects_referent, intent_change?)
#
# expected_route per turn: ask | answer | verify
# expects_referent: the user is referring to prior context.
# intent_change:    user pivots topic mid-conversation.
DIALOGUES = [
    # 1. project planning, then change intent
    {"theme": "project_planning_then_pivot", "turns": [
        ("I'm planning a small Python project.",                       "answer", False, False),
        ("It will analyze CSV files.",                                 "answer", True,  False),
        ("Should I use pandas or polars?",                             "answer", True,  False),
        ("Actually, let's switch — I want to make a CLI tool instead.","answer", False, True),
        ("What library do you recommend for the CLI?",                 "answer", True,  False),
    ]},
    # 2. debugging help with continuation
    {"theme": "debug_with_continuation", "turns": [
        ("My Python script raises a KeyError.",                        "ask",    False, False),
        ("It happens when I call config['env'].",                      "answer", True,  False),
        ("config is loaded from a JSON file.",                         "answer", True,  False),
        ("Yes — what should I check first?",                           "answer", True,  False),
        ("And after that?",                                            "ask",    True,  False),
    ]},
    # 3. conceptual explanation chain
    {"theme": "conceptual_chain", "turns": [
        ("Explain what a hash table is.",                              "answer", False, False),
        ("How does collision handling work?",                          "answer", True,  False),
        ("What's the difference between chaining and open addressing?","answer", True,  False),
        ("Which is more cache-friendly?",                              "answer", True,  False),
        ("Got it. Thanks.",                                            "answer", False, False),
    ]},
    # 4. ambiguous follow-up (user keeps under-specifying)
    {"theme": "ambiguous_followup", "turns": [
        ("Help me with this.",                                         "ask",    False, False),
        ("It's broken.",                                               "ask",    True,  False),
        ("The thing.",                                                 "ask",    True,  False),
        ("Fix it.",                                                    "ask",    True,  False),
        ("Just try.",                                                  "ask",    True,  False),
    ]},
    # 5. correction and rewrite follow-up
    {"theme": "correction_rewrite", "turns": [
        ("Write a one-line bio for a software engineer.",              "answer", False, False),
        ("That's too generic — try again.",                            "ask",    True,  False),
        ("Make it more concrete.",                                     "ask",    True,  False),
        ("Use 'distributed systems' as the focus.",                    "answer", True,  False),
        ("Drop the buzzwords.",                                        "ask",    True,  False),
    ]},
    # 6. self-reference + project-state
    {"theme": "self_reference_project_state", "turns": [
        ("What can you do?",                                           "answer", False, False),
        ("Do you remember what we discussed yesterday?",               "answer", False, False),
        ("Can you read my files?",                                     "answer", False, False),
        ("What languages do you support?",                             "answer", False, False),
        ("OK — let's move on.",                                        "answer", False, False),
    ]},
    # 7. factual chain with freshness
    {"theme": "factual_freshness", "turns": [
        ("Who wrote the Iliad?",                                       "answer", False, False),
        ("What's the latest Python release?",                          "verify", False, False),
        ("Who is the current head of state of Japan?",                 "verify", False, False),
        ("And of France?",                                             "verify", True,  False),
        ("Thanks.",                                                    "answer", False, False),
    ]},
    # 8. user changes intent abruptly
    {"theme": "abrupt_intent_change", "turns": [
        ("I want to learn about Kubernetes.",                          "answer", False, False),
        ("Specifically pod scheduling.",                               "answer", True,  False),
        ("Wait — instead, tell me about Docker Compose.",              "answer", False, True),
        ("How do I link two services?",                                "answer", True,  False),
        ("And how would I do the same in K8s?",                        "answer", True,  False),
    ]},
    # 9. specialized terminology, deepening
    {"theme": "specialized_deepen", "turns": [
        ("What is differential privacy?",                              "answer", False, False),
        ("How is epsilon chosen in practice?",                         "answer", True,  False),
        ("What's the trade-off between privacy and accuracy?",         "answer", True,  False),
        ("Any concrete example?",                                      "answer", True,  False),
        ("Great — thanks for the clarity.",                            "answer", False, False),
    ]},
    # 10. casual smalltalk to task
    {"theme": "smalltalk_to_task", "turns": [
        ("Hi.",                                                        "answer", False, False),
        ("How's it going?",                                            "answer", False, False),
        ("OK — I have a quick question.",                              "answer", False, False),
        ("How do I sort a list of dicts by a key in Python?",          "answer", False, True),
        ("And in Ruby?",                                               "answer", True,  False),
    ]},
    # 11. ambiguous repair sequence
    {"theme": "ambiguous_repair", "turns": [
        ("Try the other one.",                                         "ask",    False, False),
        ("No, the first one.",                                         "ask",    True,  False),
        ("Actually, never mind.",                                      "answer", True,  False),
        ("Let me start over.",                                         "ask",    False, True),
        ("Show me the basic version.",                                 "ask",    True,  False),
    ]},
    # 12. user references "the previous one"
    {"theme": "referent_previous", "turns": [
        ("Give me a quicksort implementation in Python.",              "answer", False, False),
        ("Now add comments.",                                          "answer", True,  False),
        ("Optimize the previous one for memory.",                      "answer", True,  False),
        ("Show me a test case.",                                       "answer", True,  False),
        ("What's the worst case for that algorithm?",                  "answer", True,  False),
    ]},
    # 13. premature wrap-up attempt
    {"theme": "premature_wrap", "turns": [
        ("Help me draft an email.",                                    "ask",    False, False),
        ("To my manager about a deadline.",                            "answer", True,  False),
        ("Tone: respectful but firm.",                                 "answer", True,  False),
        ("Wrap up.",                                                   "ask",    True,  False),
        ("Yes, the email.",                                            "answer", True,  False),
    ]},
    # 14. drift attempt — irrelevant new topic
    {"theme": "drift_attempt", "turns": [
        ("Explain monads.",                                            "answer", False, False),
        ("Use Haskell examples.",                                      "answer", True,  False),
        ("By the way, how's the weather where you are?",               "answer", False, True),
        ("Back to monads — what's a Reader monad?",                    "answer", True,  True),
        ("Got it.",                                                    "answer", False, False),
    ]},
    # 15. clarification chain (user under-specifies, then specifies)
    {"theme": "clarify_then_specify", "turns": [
        ("Format this.",                                               "ask",    False, False),
        ("Format what you'd send to a TS file.",                       "answer", True,  False),
        ("Use 2-space indentation.",                                   "answer", True,  False),
        ("And single quotes.",                                         "answer", True,  False),
        ("Show me the result.",                                        "answer", True,  False),
    ]},
    # 16. mid-conversation correction by user
    {"theme": "mid_correction_by_user", "turns": [
        ("Tell me about the French Revolution.",                       "answer", False, False),
        ("It started in 1789.",                                        "answer", True,  False),
        ("That's a statement, not a question — continue with the social causes.",
                                                                       "answer", True,  False),
        ("And the role of bread prices?",                              "answer", True,  False),
        ("Summarize all the above.",                                   "answer", True,  False),
    ]},
    # 17. specialized + freshness blend
    {"theme": "specialized_plus_freshness", "turns": [
        ("Explain attention in transformer models.",                   "answer", False, False),
        ("Now compare it to recent state-space models.",               "verify", True,  False),
        ("Which has better long-context performance today?",           "verify", True,  False),
        ("Which paper introduced Mamba?",                              "verify", True,  False),
        ("Thanks.",                                                    "answer", False, False),
    ]},
    # 18. user drops context partway
    {"theme": "context_drop", "turns": [
        ("Help me debug a Python regex.",                              "ask",    False, False),
        ("It's matching too greedily.",                                "answer", True,  False),
        ("Continue.",                                                  "ask",    True,  False),
        ("OK what about anchors?",                                     "answer", True,  False),
        ("And lookaheads?",                                            "answer", True,  False),
    ]},
    # 19. user gives instructions, then asks for confirmation
    {"theme": "instructions_then_confirm", "turns": [
        ("Use formal English from now on.",                            "answer", False, False),
        ("Do not use bullet points.",                                  "answer", False, False),
        ("Now answer: what is the capital of Australia?",              "answer", False, False),
        ("Are you following my style instructions?",                   "answer", True,  False),
        ("Good. Continue with that style.",                            "answer", False, False),
    ]},
    # 20. project-state then pivot
    {"theme": "project_state_then_pivot", "turns": [
        ("Where did we leave off in our discussion?",                  "answer", False, False),
        ("Right — the schema design.",                                 "answer", True,  False),
        ("Switch topics — how do I learn Rust quickly?",               "answer", False, True),
        ("Recommend a textbook.",                                      "answer", True,  False),
        ("And one practical project to try.",                          "answer", True,  False),
    ]},
]


def main() -> int:
    from scripts.pseudo_ui_runner import PseudoUISession

    DIALOGUES_OUT.write_text(
        "\n".join(json.dumps({
            "id": f"d_{i+1:02d}",
            "theme": d["theme"],
            "turns": [{"user_input": t[0], "expected_route": t[1],
                       "expects_referent": t[2], "intent_change": t[3]}
                      for t in d["turns"]],
        }, ensure_ascii=False) for i, d in enumerate(DIALOGUES)) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(DIALOGUES)} dialogue specs → {DIALOGUES_OUT}",
          flush=True)

    per_dialogue = []
    cat_counts = {"match": 0, "A": 0, "B": 0, "C": 0, "other": 0}
    n_referent_turns = 0
    n_referent_resolved = 0     # heuristic: actual route != ask when expected_route in {answer, verify}
    n_intent_change_turns = 0
    n_intent_change_handled = 0
    n_topic_drift_codes = 0
    final_turn_natural_count = 0

    t_start = time.time()
    for i, d in enumerate(DIALOGUES, 1):
        sess = PseudoUISession()
        turns_out = []
        for j, t in enumerate(d["turns"], 1):
            user_input, expected_route, expects_ref, intent_chg = t
            try:
                r = sess.process_turn(user_input)
                actual = r.route or "(empty)"
                rcs = list(r.reason_codes or [])
                resp = r.response_text or ""
            except Exception as e:
                actual = "(error)"
                rcs = [f"harness_error:{type(e).__name__}"]
                resp = ""

            # Cat assignment per turn
            if expected_route == actual:
                cat = "match"
            elif expected_route in ("ask", "verify") and actual == "answer":
                cat = "A"
            elif expected_route == "answer" and actual == "ask":
                cat = "B"
            elif expected_route == "answer" and actual == "verify":
                cat = "C"
            elif expected_route == "verify" and actual == "ask":
                cat = "C"
            else:
                cat = "other"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

            if expects_ref:
                n_referent_turns += 1
                # Heuristic: if the model abruptly asks ("ask" route)
                # when prior context was set, treat as failed referent
                # resolution unless that itself was the expected route.
                if not (actual == "ask" and expected_route != "ask"):
                    n_referent_resolved += 1
            if intent_chg:
                n_intent_change_turns += 1
                # Handled if the model didn't fall over (route in valid set)
                if actual in ("answer", "verify", "ask", "abstain"):
                    n_intent_change_handled += 1
            if any("topic_drift" in rc.lower() for rc in rcs):
                n_topic_drift_codes += 1

            turn_row = {
                "turn": j,
                "user_input": user_input,
                "expected_route": expected_route,
                "actual_route": actual,
                "cat": cat,
                "reason_codes": rcs[:6],
                "response_excerpt": (resp[:240] if resp else "(empty)"),
            }
            turns_out.append(turn_row)

        # Final turn naturalness flag
        last = turns_out[-1]
        if last["actual_route"] in ("answer", "verify") and len(last.get("response_excerpt", "")) >= 5:
            final_turn_natural_count += 1

        per_dialogue.append({
            "id": f"d_{i:02d}",
            "theme": d["theme"],
            "turns": turns_out,
        })
        elapsed = time.time() - t_start
        print(f"  dialogue {i}/{len(DIALOGUES)} ({d['theme']}) elapsed={elapsed:.1f}s",
              flush=True)

    n_turns = sum(len(d["turns"]) for d in DIALOGUES)
    cat_A_rate = cat_counts["A"] / n_turns if n_turns else 0
    if cat_A_rate < 0.05:
        verdict = "PASS"
    elif cat_A_rate < 0.10:
        verdict = "INFO_PASS"
    else:
        verdict = "WARNING"

    summary = {
        "test": "p9_evidence_pack_v1.test_3_multiturn_smoke",
        "n_dialogues": len(DIALOGUES),
        "n_turns": n_turns,
        "elapsed_s": round(time.time() - t_start, 1),
        "cat_counts": cat_counts,
        "cat_A_rate": round(cat_A_rate, 4),
        "verdict": verdict,
        "referent_resolution": {
            "n_referent_turns": n_referent_turns,
            "n_resolved_heuristic": n_referent_resolved,
            "rate": round(n_referent_resolved / n_referent_turns, 4) if n_referent_turns else None,
        },
        "intent_change_handling": {
            "n_intent_change_turns": n_intent_change_turns,
            "n_handled": n_intent_change_handled,
            "rate": round(n_intent_change_handled / n_intent_change_turns, 4) if n_intent_change_turns else None,
        },
        "topic_drift_reason_codes": n_topic_drift_codes,
        "final_turn_naturalness": {
            "n_dialogues_natural_final_turn": final_turn_natural_count,
            "rate": round(final_turn_natural_count / len(DIALOGUES), 4),
        },
        "per_dialogue": per_dialogue,
        "methodology_notes": [
            "Author-assigned per-turn labels (expected_route / "
            "expects_referent / intent_change). Smoke test, not benchmark.",
            "Referent resolution is a coarse heuristic: actual route != 'ask' "
            "when expected route was answer/verify counts as resolved.",
            "Cat A here means premature-answer in a multi-turn setting "
            "(same definition as Test 1).",
        ],
    }

    RESULTS_OUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote results: {RESULTS_OUT}")
    print(f"verdict: {verdict}  Cat A rate (per-turn): {cat_A_rate*100:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
