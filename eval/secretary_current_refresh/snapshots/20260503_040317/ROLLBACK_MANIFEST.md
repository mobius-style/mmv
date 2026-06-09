# Rollback manifest


_Snapshot timestamp:_ `20260503_040317`

_Repo HEAD at snapshot:_ `2047f3092341e20ccbba5b4890adb6cf33fdec0e`

_RC3 commit:_ `7f53fe1dbdf189f014b0cd2643a996148fc5dba7`

## Files in scope

- `docs/current/RELEASE_STATUS.md` — changed: **yes** 
  - before SHA-256: `208060cca258dc7c3c9999204ef9b525ccbf988dbc90846929916d84d568e236` 
  - after  SHA-256: `ff2fc03d1e8cd3153d2e06394193f4d451c32062fdfdfe2fb867fdf9ad5c879b`
- `docs/current/DOCS_AUTHORITY_MAP.md` — changed: **yes** 
  - before SHA-256: `0f2cfcce66a81ad2f55a04318238d112faf02bd39d61ad322a9bb83be71ee418` 
  - after  SHA-256: `fe3c94f765386a5a4529c16b7349550a79befdaf68b76d90f5904838c2657459`
- `docs/current/PUBLIC_RELEASE_READINESS.md` — changed: **yes** 
  - before SHA-256: `5ec81ff35b5e79d161ac782e94d66c1f4c4c82a04f8b4822241e94fcddde0d92` 
  - after  SHA-256: `b4d5de1bca4ade75b077b45ea89ae3fe7d335a680a54999719121f25370fa9bd`
- `docs/current/SETUP_GAPS.md` — changed: **yes** 
  - before SHA-256: `e68c54814cf8ab58a0f5dc426252f96e1845158aebe00f5989609bd25fbcbed4` 
  - after  SHA-256: `f549e0df9e377498187ad5810c22ef3c3c58e45483fa24d98b7d05a69d92dba6`

## How to roll back

```bash
# inspect what would happen (no writes)
./eval/secretary_current_refresh/snapshots/20260503_040317/rollback.sh --check

# perform rollback
./eval/secretary_current_refresh/snapshots/20260503_040317/rollback.sh
```

The rollback restores the four `docs/current/*.md` files from the `before/` directory captured by this snapshot. **No `git` commands are run.** T should review the resulting working tree with `git diff docs/current/` and decide whether to commit, revert further, or leave as-is.
