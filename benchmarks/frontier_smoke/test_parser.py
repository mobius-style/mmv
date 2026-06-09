"""30+ unit tests for the frontier smoke parser (Phase 2 self-test).

Run: python -m benchmarks.frontier_smoke.test_parser
"""
from __future__ import annotations

import sys
import traceback

from .parser import (
    apply_routing_precedence,
    parse_letter,
    parse_number,
    score_simpleqa,
)


FAIL = []


def expect(name: str, got, want):
    if got != want:
        FAIL.append(f"  [{name}] got={got!r} want={want!r}")


def main() -> int:
    print("=== layered letter parser ===")
    # L1 exact
    expect("L1.exact", parse_letter("B").parsed, "B")
    expect("L1.exact.dot", parse_letter("B.").parsed, "B")
    expect("L1.exact.paren", parse_letter("B)").parsed, "B")
    expect("L1.exact.space", parse_letter("  B  ").parsed, "B")
    # L2 bold
    expect("L2.bold", parse_letter("The answer **C** seems right.").parsed, "C")
    # L3 tagged
    expect("L3.tagged.colon", parse_letter("Answer: D").parsed, "D")
    expect("L3.tagged.is", parse_letter("the answer is E").parsed, "E")
    expect("L3.tagged.paren", parse_letter("correct answer is (F)").parsed, "F")
    expect("L3.tagged.choose", parse_letter("I choose G after thought.").parsed, "G")
    expect("L3.tagged.option", parse_letter("Option H is closest.").parsed, "H")
    # L4 parenthesized terminal
    expect("L4.terminal", parse_letter("After analysis, this gives us (B).").parsed, "B")
    # L5 boxed
    expect("L5.boxed", parse_letter("\\boxed{D}").parsed, "D")
    # L6 last standalone + negation guard
    expect("L6.last.gemma",
           parse_letter("Between A and B, I would choose B").parsed, "B")
    # negation guard is conservative — a 'not' within 30 chars BEFORE the
    # last standalone letter kills it, even when 'not' modified a DIFFERENT
    # letter earlier. This is by design (spec §4.1) — false-negatives
    # accepted to keep parse precision high.
    expect("L6.negation.conservative",
           parse_letter("It is not A, the answer must be B").layer,
           "parse_failure")
    # negation should suppress the WRONG one
    expect("L6.negation.kill",
           parse_letter("This is not A").layer, "parse_failure")
    # parse failure: only J in valid for letters A-J — empty/garbage
    expect("L7.fail.garbage", parse_letter("xyz!!!").layer, "parse_failure")
    expect("L7.fail.empty", parse_letter("").layer, "parse_failure")
    # GPQA letters A-D only
    expect("GPQA.A", parse_letter("A", "ABCD").parsed, "A")
    expect("GPQA.outside",
           parse_letter("The answer is E", "ABCD").layer, "parse_failure")

    print("=== number parser ===")
    expect("N1.exact", parse_number("3", 5).parsed, "3")
    expect("N2.bold", parse_number("**4**", 5).parsed, "4")
    expect("N3.tagged", parse_number("Answer: 2", 5).parsed, "2")
    expect("N3.option", parse_number("Option 1 fits.", 5).parsed, "1")
    expect("N4.first", parse_number("Looking at 5, this is best", 5).parsed, "5")
    # out-of-range digits are skipped, first in-range wins
    expect("N4.skip_out_of_range",
           parse_number("In 2023, the answer is 5.", 5).parsed, "5")
    expect("N4.all_out_of_range",
           parse_number("In 2023 the answer is unclear", 5).layer,
           "parse_failure")
    expect("N7.fail", parse_number("none of these", 5).layer, "parse_failure")

    print("=== SimpleQA scorer ===")
    # routing override beats all
    expect("SQ.routing", score_simpleqa("Paris", "Paris", "ask").verdict,
           "routing_override")
    # empty
    expect("SQ.empty", score_simpleqa("", "Paris").verdict, "incorrect")
    # abstain
    expect("SQ.abstain",
           score_simpleqa("I don't know.", "Paris").verdict, "abstain")
    expect("SQ.abstain.no_verify",
           score_simpleqa("I cannot verify this.", "x").verdict, "abstain")
    # exact normalized (case + articles + punctuation)
    expect("SQ.exact",
           score_simpleqa("the Eiffel Tower.", "eiffel tower").verdict,
           "correct")
    # substring word-boundary
    r = score_simpleqa("The capital is Paris, France.", "Paris")
    expect("SQ.substring", r.verdict, "correct")
    expect("SQ.substring.layer", r.scoring_layer, "substring_word_boundary")
    # negation guard
    expect("SQ.neg_guard",
           score_simpleqa("The answer is not Paris but Lyon.", "Paris").verdict,
           "incorrect")
    # short gold + late match → judge_review
    long_pre = "x" * 60
    r = score_simpleqa(f"{long_pre} XYZ", "XYZ")
    expect("SQ.short_late", r.verdict, "judge_review")
    expect("SQ.short_late.layer", r.scoring_layer, "short_gold_late_match")
    # verbose response + single-token gold + no L5 match
    verbose = "This is a long verbose response that rambles on " * 5
    r = score_simpleqa(verbose, "Tokyo")
    expect("SQ.verbose", r.verdict, "judge_review")
    expect("SQ.verbose.layer", r.scoring_layer,
           "verbose_with_single_token_gold")

    print("=== routing precedence ===")
    expect("R.answer.passes", apply_routing_precedence("answer"), None)
    expect("R.none.passes", apply_routing_precedence(None), None)
    r = apply_routing_precedence("ask")
    expect("R.ask.override", r.layer, "routing_override")
    expect("R.ask.parsed", r.parsed, None)

    if FAIL:
        print(f"\nFAIL — {len(FAIL)} assertion(s) failed:")
        for f in FAIL:
            print(f)
        return 1
    print("\nALL TESTS PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
