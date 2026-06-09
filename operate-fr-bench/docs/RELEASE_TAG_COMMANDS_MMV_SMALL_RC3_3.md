# MMV Small RC3.3 — Suggested git tag commands

These are **suggested commands only**. They are not executed by this
agent run. The maintainer should review the artifacts and execute
them manually when ready.

## Safety preconditions before tagging

- The freeze note has been read and approved.
- The smoke report has been read and approved.
- The human review packet has been inspected (or its absence
  consciously accepted as a known limitation).
- `pytest operate-fr-bench/tests/` is green.
- No untracked secrets are in the staged files.
- The repository's branch is in the desired state to be tagged.

## Suggested commands (do NOT execute without review)

```bash
# 1. Sanity check working tree
git status

# 2. Re-run the OPERATE-FR test suite
pytest operate-fr-bench/tests/

# 3. Stage the freeze artifacts only
git add operate-fr-bench/docs/MMV_Small_RC3_3_FREEZE_NOTE.md \
        operate-fr-bench/releases/small/current.yaml \
        operate-fr-bench/reports/MMV_Small_RC3_3_smoke_report.md \
        operate-fr-bench/reports/human_review_packet_mmv_small_rc3_3 \
        operate-fr-bench/docs/RELEASE_TAG_COMMANDS_MMV_SMALL_RC3_3.md

# (optional) Stage the v1 + v1.1 evidence artifacts if not already
# committed:
#   git add operate-fr-bench/harness/small_routing_stabilizer.py \
#           operate-fr-bench/harness/run_eval.py \
#           operate-fr-bench/configs/model_profiles.example.yaml \
#           operate-fr-bench/tests/test_small_routing_stabilizer.py \
#           operate-fr-bench/tests/test_small_rc3_3_v1_1_query_neutrality.py \
#           operate-fr-bench/reports/small_9b_rescore_baseline_20260516T051333Z.md \
#           operate-fr-bench/reports/small_9b_failure_audit_20260516T051447Z.md \
#           operate-fr-bench/reports/ablation_small_rc3_3_v1_20260516T052933Z.md \
#           operate-fr-bench/reports/mmv_small_rc3_3_stabilized.jsonl \
#           operate-fr-bench/reports/mmv_small_rc3_3_stabilized_summary.json \
#           operate-fr-bench/reports/small_rc3_3_v1_1_query_neutrality_audit_20260516T054947Z.md \
#           operate-fr-bench/reports/ablation_small_rc3_3_v1_1_20260516T060408Z.md \
#           operate-fr-bench/reports/mmv_small_rc3_3_stabilized_v1_1.jsonl \
#           operate-fr-bench/reports/mmv_small_rc3_3_stabilized_v1_1_summary.json

# 4. Commit
git commit -m "Freeze MMV Small RC3.3 routing stabilization update"

# 5. Annotated tag
git tag -a mmv-small-rc3.3-routing-stabilization-20260516 \
        -m "MMV Small RC3.3 — Routing Stabilization Update"

# 6. Verify
git status
git log -1 --decorate --stat
git tag --list 'mmv-small-rc3.3-*' --verbose
```

## What this RC tag does NOT authorise

- **No `git push`.** Pushing the tag is a separate, explicit step.
- **No GitHub Release.** Do not create a release on github.com.
- **No Zenodo deposit.** No DOI publication on Zenodo or any other
  archive.
- **No public announcement.** MMV-S-RC3.3 is a Smoke-100 candidate
  engineering RC, not a public release.
- **No standard-benchmark claim.** Tag wording deliberately includes
  "RC3.3" and "Routing Stabilization Update", not "validated" /
  "official" / "standard".

## If pytest fails

Do NOT tag. Investigate the failing test, fix or rollback the cause,
and re-run from step 2. The tag should only be applied to a green
state.

## If the working tree contains unrelated changes

Either commit them separately under a different message, or stash
them and re-run the freeze sequence on a clean tree. Mixing the
RC3.3 freeze commit with unrelated changes makes the tag impossible
to reason about later.

## Rollback

If the tag is created and then needs to be removed (locally only,
not pushed):

```bash
git tag -d mmv-small-rc3.3-routing-stabilization-20260516
git reset --soft HEAD~1   # if also reverting the commit
```

Do not run these unless you are certain. Tag deletion is destructive.

## Relation to the MMV Large RC3.3 tag

The MMV-S-RC3.3 tag is **independent** of the MMV-L-RC3.3 tag
(`mmv-large-rc3.3-temporal-governance-20260516`). The two releases
cover different model paths (Small / 9B vs Large / 120B) with
different governance layers (Stabilizer vs route transformer + post-
emission validator). Both tags may coexist on the same commit if the
freeze artifacts for both are committed together; otherwise tag them
on separate commits in chronological order.
