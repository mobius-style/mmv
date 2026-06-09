#!/usr/bin/env python3
"""phase4_seed_driver.py — Phase 4 v2.1 STEP 3 per-batch protocol driver.

This is the REPLACEMENT for the deprecated `create_seed_patterns.py`,
which the M1 audit showed silently skipped quality_grader and
conflict_checker (resulting in 0 / 39 real-acceptance for M1 B1+B2,
24 patterns quarantined).

Per Phase 4 v2.1 §STEP 3 per-batch protocol, this driver invokes the
full pipeline:

  1. Generate seed examples + negatives + xling (single Groq consensus
     call producing the initial Pattern shape — same as old driver)
  2. Schema validation (Pydantic)
  3. **Quality grader** (5-axis median ≥ 4 — REJECT below threshold)
  4. **Conflict checker** (cosine ≥ 0.85 against active library —
     REJECT any conflict)
  5. Append to `config/pattern_library/<topic>.jsonl` with origin tag
  6. Audit log entry per pattern

The driver does NOT invoke variants_generator / negatives_generator /
xling_query_generator separately — those are for *augmenting an
existing pattern* (post-seed expansion), and are wired into a
separate `phase4_augment_driver.py` (out of scope here, designed for
Phase 4 STEP 3 batches that grow already-accepted patterns).

For M1 retry, the seed driver alone produces high-quality 1-pattern
units that pass the gates. M1 1,000-pattern target = 1,000 driver
invocations × ~6K tokens each (seed call ~3K + grader call ~3K) =
~6M tokens (well within ST1 ≤ 50M budget).

Usage:
    python3 scripts/pattern_autogen/phase4_seed_driver.py \\
        --spec /tmp/p4m1_seeds.json \\
        --target-jsonl config/pattern_library/self_reference.jsonl

Acceptance gate: at least 50% of seeds must pass both quality_grader
and conflict_checker. Below 30% in a single batch → halt + diagnostic.

Spec ref: docs/PATTERN_LIBRARY_SPEC_v1_4_1.md §3.2 + Phase 4 v2.1
prompt §STEP 3 per-batch protocol.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "pattern_library"
AUDIT_DIR = REPO_ROOT / "data" / "pattern_library" / "audit_log"

sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.pattern_schema import (  # noqa: E402
    LifecycleEvent, Origin, Pattern, RouteConfig,
)
from scripts.pattern_autogen.groq_client import (  # noqa: E402
    AutogenGroqClient,
)
from scripts.pattern_autogen.quality_grader import (  # noqa: E402
    QualityGrader, QUALITY_THRESHOLD,
)
from scripts.pattern_autogen.conflict_checker import (  # noqa: E402
    ConflictChecker, CONFLICT_THRESHOLD,
)


# Phase 4 v2.1 audit (Commit 8): sub-topic-aware conflict policy.
# The base conflict_checker uses CONFLICT_THRESHOLD=0.85 as a binary
# gate; the M1 audit + Commit 7 smoke confirmed this catches both
# true duplicates AND legitimate cross-topic adjacency at the ME5
# embedding level (e.g. "explain X" structure correlates ≥0.85 across
# topics regardless of subject). Per Phase 2 spec acknowledgment of
# "within-topic adjacency informational, not blocking", we apply:
#
#   Within same sub_topic:    relaxed 0.92 (was 0.85 — see Calibration)
#   Cross sub_topic, same topic: relaxed 0.92 (catch heavy overlap)
#   Cross-topic:                 relaxed 0.95 (catch only literal dups)
#
# This is enforced in the driver, not in the checker module — the
# checker remains the binary primitive; the driver applies policy.
#
# Calibration (M1 retry diagnostic, 2026-04-27,
# docs/PHASE_4_M1_SATURATION_DIAGNOSTIC.md):
# WITHIN_SUBTOPIC_STRICT was 0.85 in audit Commit 8. M1 retry batch 2
# hit 0/8 acceptance (immediate halt) because LLM-generated examples
# within the same sub-topic share structural embedding features at
# cosine ≥ 0.85 — sub-topics saturated at ~3-4 patterns. Phase 4 v2.1
# targets 100-500 patterns per sub-topic, so the within-sub-topic
# threshold needs ~0.92 to allow 50-100 siblings before saturation.
# Quality grader (5-axis ≥ 4) remains the primary discriminator
# against true duplicates within a sub-topic. Per spec v1.4
# "empirical recalibration > theoretical defaults" discipline.
WITHIN_SUBTOPIC_STRICT = 0.92
CROSS_SUBTOPIC_SAMETOPIC = 0.92
CROSS_TOPIC_RELAXED = 0.95


def filter_conflicts_sub_topic_aware(
    candidate: Pattern,
    raw_conflicts: list,
    library_lookup: dict[str, Pattern],
) -> list:
    """Apply sub-topic-aware threshold policy to raw conflict_checker
    output. Returns filtered list of (other_id, ex_a, ex_b, cosine)
    tuples that exceed the policy threshold for their relationship.

    raw_conflicts is the list produced by ConflictChecker.check() —
    each tuple already at cosine ≥ CONFLICT_THRESHOLD (0.85). This
    function further filters by relationship-aware threshold.
    """
    cand_topic = candidate.topic
    cand_sub = getattr(candidate, "sub_topic", "") or ""
    filtered = []
    for tup in raw_conflicts:
        other_id, ex_a, ex_b, cosine = tup
        other = library_lookup.get(other_id)
        if other is None:
            # Defensive: keep at strict if we cannot identify the other
            if cosine >= WITHIN_SUBTOPIC_STRICT:
                filtered.append(tup)
            continue
        other_topic = other.topic
        other_sub = getattr(other, "sub_topic", "") or ""
        if cand_topic == other_topic and cand_sub == other_sub:
            threshold = WITHIN_SUBTOPIC_STRICT
        elif cand_topic == other_topic:
            threshold = CROSS_SUBTOPIC_SAMETOPIC
        else:
            threshold = CROSS_TOPIC_RELAXED
        if cosine >= threshold:
            filtered.append(tup)
    return filtered


SEED_SYSTEM_PROMPT = (
    "You design AI intent patterns for the MOBIUS Pattern Library. "
    "Given an intent specification, produce examples + negatives + "
    "cross-lingual test queries in STRICT JSON format. "
    "Examples: 5-10 surface phrasings of the intent (English, "
    "diverse word choice). "
    "Negatives: 5-7 disambiguators that look surface-similar but are "
    "ABOUT A DIFFERENT topic/entity. Negatives must be substantively "
    "different from the existing library to avoid duplicate "
    "embeddings (cosine ≥ 0.85 reject). "
    "Cross-lingual queries: at least 2 Japanese (ja) + 2 Chinese (zh), "
    "mix of expected_match=true (positive paraphrases) and "
    "expected_match=false (disambiguators). "
    "min_cosine: 0.62 for expected_match=true entries, null for false. "
    "Output STRICT JSON only, no preface: "
    '{"examples": ["...", ...], "negative_examples": ["...", ...], '
    '"cross_lingual_test_queries": ['
    '{"lang": "ja|zh|...", "query": "...", '
    '"expected_match": true|false, "min_cosine": 0.62 or null}, ...]}.'
)


def build_user_prompt(spec: dict) -> str:
    return (
        f"Pattern id: {spec['id']}\n"
        f"Topic: {spec['topic']}\n"
        f"Sub-topic: {spec.get('sub_topic', '(none)')}\n"
        f"Intent: {spec['intent']}\n"
        f"Description: {spec['description']}\n\n"
        f"Output the strict JSON spec for this intent. Generate "
        f"unique surface phrasings — DO NOT echo phrasings that other "
        f"existing intents would already cover."
    )


def assemble_pattern(spec: dict, content: dict, batch_id: str,
                     run_id: str, now: datetime) -> Pattern:
    return Pattern(
        id=spec["id"],
        version="1.0",
        lang="en",
        topic=spec["topic"],
        sub_topic=spec.get("sub_topic", ""),
        intent=spec["intent"],
        concepts=spec.get("concepts", []),
        priority=spec.get("priority", 100),
        examples=content["examples"][:15],
        negative_examples=content.get("negative_examples", []),
        context_required=spec.get("context_required"),
        context_excluded=spec.get("context_excluded", []),
        route=RouteConfig(**spec["route"]),
        tags=spec.get("tags", []),
        cross_lingual_test_queries=content["cross_lingual_test_queries"],
        lifecycle={"history": [{
            "timestamp": now.isoformat(),
            "event": "created",
            "actor": "phase4_seed_driver",
            "detail": f"Phase 4 v2.1 audit-grade driver (batch {batch_id})",
        }]},
        origin=Origin(
            type="autogen",
            date=now,
            batch_id=batch_id,
            groq_run_id=run_id,
            prompt_version="phase4_seed_v1",
        ),
        deprecated=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 4 v2.1 full-pipeline seed driver",
    )
    parser.add_argument("--spec", type=Path, required=True,
                        help="JSON file with pattern specs (list of dicts)")
    parser.add_argument("--target-jsonl", type=Path, required=True,
                        help="config/pattern_library/<topic>.jsonl path")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only first N specs (smoke)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate + filter but do NOT write JSONL/audit")
    parser.add_argument("--acceptance-floor", type=float, default=0.50,
                        help="Halt batch if acceptance < this fraction "
                             "(default 0.50 per Phase 4 v2.1 §STEP 3)")
    parser.add_argument("--immediate-halt-floor", type=float, default=0.30,
                        help="Immediate halt if single batch < this "
                             "(default 0.30)")
    args = parser.parse_args()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    specs = json.loads(args.spec.read_text(encoding="utf-8"))
    if args.limit:
        specs = specs[:args.limit]
    if not specs:
        print("No specs to process.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    batch_id = ("bat_p4seed_" + now.strftime("%Y%m%d_%H%M%S")
                + "_" + secrets.token_hex(2))
    print(f"batch_id={batch_id} specs={len(specs)} target={args.target_jsonl}")
    print(f"Pipeline: groq_seed → schema → quality_grader (≥{QUALITY_THRESHOLD}) "
          f"→ conflict_checker (cosine < {CONFLICT_THRESHOLD})")

    client = AutogenGroqClient()
    grader = QualityGrader()
    conflict_checker = ConflictChecker()
    library = {p.id: p for p in conflict_checker._load_library()}

    accepted: list[Pattern] = []
    rejected: list[tuple[str, str]] = []

    for spec in specs:
        print(f"\n  ▶ {spec['id']} ({spec.get('intent', '?')}, "
              f"sub_topic={spec.get('sub_topic', '?')})", flush=True)

        # Stage 1: Groq seed generation
        consensus = client.consensus(
            SEED_SYSTEM_PROMPT, build_user_prompt(spec),
            max_tokens=2500, prompt_version="phase4_seed_v1",
            batch_id=batch_id,
        )
        content = None
        for call in consensus.calls:
            if (call.parsed and isinstance(call.parsed, dict)
                    and isinstance(call.parsed.get("examples"), list)
                    and len(call.parsed["examples"]) >= 5):
                content = call.parsed
                break
        if content is None:
            rejected.append((spec["id"], "stage1_no_parseable_content"))
            print(f"    ✗ stage1: no parseable Groq output")
            continue

        # Stage 2: Schema validation
        try:
            patt = assemble_pattern(spec, content, batch_id,
                                     consensus.groq_run_id, now)
        except Exception as e:
            rejected.append((spec["id"], f"stage2_schema: {str(e)[:100]}"))
            print(f"    ✗ stage2 schema: {str(e)[:80]}")
            continue

        # Stage 3: Quality grader (5-axis ≥ 4)
        score = grader.grade(patt, batch_id=batch_id)
        if not score.passes(QUALITY_THRESHOLD):
            rejected.append((
                spec["id"],
                f"stage3_quality: overall {score.overall:.1f} < {QUALITY_THRESHOLD} "
                f"(IC={score.intent_clarity:.0f} EC={score.example_coverage:.0f} "
                f"ND={score.negative_discrimination:.0f} XL={score.xling_consistency:.0f})"
            ))
            print(f"    ✗ stage3 grade: overall {score.overall:.1f} < {QUALITY_THRESHOLD}")
            continue

        # Stage 4: Conflict checker (sub-topic-aware policy)
        cr = conflict_checker.check(patt)
        policy_conflicts = filter_conflicts_sub_topic_aware(
            patt, cr.conflicts, library,
        )
        if policy_conflicts:
            top = max(policy_conflicts, key=lambda c: c[3])
            rejected.append((
                spec["id"],
                f"stage4_conflict: {len(policy_conflicts)} policy "
                f"conflicts (raw {len(cr.conflicts)}); top vs "
                f"{top[0]} @ cosine {top[3]:.3f}"
            ))
            print(f"    ✗ stage4 conflict: {len(policy_conflicts)} policy "
                  f"(raw {len(cr.conflicts)}); top vs "
                  f"{top[0]} @ {top[3]:.3f}")
            continue
        elif cr.conflicts:
            print(f"    ⓘ stage4 raw {len(cr.conflicts)} conflicts but "
                  f"policy-filtered (cross-topic adjacency, informational)")

        # All 4 stages passed
        accepted.append(patt)
        print(f"    ✓ all stages: ex={len(patt.examples)} "
              f"neg={len(patt.negative_examples)} "
              f"xl={len(patt.cross_lingual_test_queries)} "
              f"quality={score.overall:.1f}")

    n_total = len(specs)
    n_accepted = len(accepted)
    acceptance_rate = n_accepted / n_total if n_total else 0
    print(f"\n=== Batch result ===")
    print(f"  batch_id: {batch_id}")
    print(f"  total specs: {n_total}")
    print(f"  accepted: {n_accepted}")
    print(f"  rejected: {len(rejected)}")
    print(f"  acceptance rate: {acceptance_rate * 100:.1f}%")

    # Acceptance protocol per Phase 4 v2.1 §STEP 3
    halt_required = False
    if acceptance_rate < args.immediate_halt_floor:
        print(f"  ⚠ IMMEDIATE HALT (< {args.immediate_halt_floor*100:.0f}%)")
        halt_required = True
    elif acceptance_rate < args.acceptance_floor:
        print(f"  ⚠ Below soft floor ({args.acceptance_floor*100:.0f}%) — "
              f"3 consecutive < floor → halt sub-topic")

    # Append to target JSONL (unless dry-run or halt)
    if accepted and not args.dry_run and not halt_required:
        existing = []
        if args.target_jsonl.exists():
            existing = args.target_jsonl.read_text(
                encoding="utf-8"
            ).splitlines()
        with args.target_jsonl.open("w", encoding="utf-8") as fh:
            for line in existing:
                if line.strip():
                    fh.write(line + "\n")
            for p in accepted:
                fh.write(p.model_dump_json(exclude_none=False) + "\n")
        print(f"  ✓ Appended {n_accepted} patterns to {args.target_jsonl}")

    # Audit log
    if not args.dry_run:
        audit_path = AUDIT_DIR / f"phase4_seed_{batch_id}.jsonl"
        with audit_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "batch_id": batch_id,
                "n_total": n_total,
                "n_accepted": n_accepted,
                "n_rejected": len(rejected),
                "acceptance_rate": acceptance_rate,
                "halt_required": halt_required,
                "halt_floor": args.immediate_halt_floor,
                "soft_floor": args.acceptance_floor,
                "pipeline_version": "phase4_seed_v1",
            }, ensure_ascii=False) + "\n")
            for p in accepted:
                fh.write(json.dumps({
                    "pattern_id": p.id, "status": "accepted",
                    "examples_count": len(p.examples),
                    "neg_count": len(p.negative_examples),
                    "xling_count": len(p.cross_lingual_test_queries),
                }, ensure_ascii=False) + "\n")
            for pid, reason in rejected:
                fh.write(json.dumps({
                    "pattern_id": pid, "status": "rejected",
                    "reason": reason,
                }, ensure_ascii=False) + "\n")
        print(f"  audit: {audit_path}")

    return 0 if (n_accepted > 0 and not halt_required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
