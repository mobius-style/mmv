# MMV Large RC3.3 — Suggested git tag commands

These are **suggested commands only**. They are not executed by this
agent run. The maintainer should review the artifacts and execute them
manually when ready.

## Safety preconditions before tagging

- The freeze note has been read and approved.
- The smoke report has been read and approved.
- The human review packet has been inspected (or its absence
  consciously accepted as a known limitation).
- `pytest operate-fr-bench/tests/` is green.
- No untracked secrets are in the staged files.
- The repository's `main` branch is in the desired state to be tagged.

## Suggested commands (do NOT execute without review)

```bash
# 1. Sanity check working tree
git status

# 2. Re-run the OPERATE-FR test suite
pytest operate-fr-bench/tests/

# 3. Stage the freeze artifacts only
git add operate-fr-bench/docs/MMV_Large_RC3_3_FREEZE_NOTE.md \
        operate-fr-bench/reports/MMV_Large_RC3_3_smoke_report.md \
        operate-fr-bench/reports/human_review_packet_mmv_large_rc3_3 \
        operate-fr-bench/docs/RELEASE_TAG_COMMANDS_MMV_LARGE_RC3_3.md

# (optional) Stage the v3.1 code + ablation artifacts if not already
# committed:
#   git add operate-fr-bench/harness/classify_route.py \
#           operate-fr-bench/harness/route_transformer.py \
#           operate-fr-bench/harness/adapters.py \
#           operate-fr-bench/harness/run_eval.py \
#           operate-fr-bench/configs/model_profiles.example.yaml \
#           operate-fr-bench/tests/test_v3_1_freshness_refuse.py \
#           operate-fr-bench/reports/ablation_120b_v3_1_20260516T043345Z.md \
#           operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_1.jsonl \
#           operate-fr-bench/reports/120b_route_transformer_plus_validator_v3_1_summary.json \
#           operate-fr-bench/reports/*_v3_1_rescored* \
#           operate-fr-bench/reports/backups

# 4. Commit
git commit -m "Freeze MMV Large RC3.3 temporal governance update"

# 5. Annotated tag
git tag -a mmv-large-rc3.3-temporal-governance-20260516 \
        -m "MMV Large RC3.3 — Temporal Governance Update"

# 6. Verify
git status
git log -1 --decorate --stat
git tag --list 'mmv-large-rc3.3-*' --verbose
```

## What this RC tag does NOT authorise

- **No `git push`.** Pushing the tag is a separate, explicit step.
- **No GitHub Release.** Do not create a release on github.com.
- **No Zenodo deposit.** No DOI publication on Zenodo or any other
  archive.
- **No public announcement.** RC3.3 is a Smoke-100 candidate
  engineering RC, not a public release.
- **No standard-benchmark claim.** Tag wording deliberately includes
  "RC3.3" and "Temporal Governance Update", not "validated" /
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
git tag -d mmv-large-rc3.3-temporal-governance-20260516
git reset --soft HEAD~1   # if also reverting the commit
```

Do not run these unless you are certain. Tag deletion is destructive.
