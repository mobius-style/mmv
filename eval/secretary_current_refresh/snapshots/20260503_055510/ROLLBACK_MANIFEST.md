# Rollback manifest


_Snapshot timestamp:_ `20260503_055510`

_Repo HEAD at snapshot:_ `b0afc33c64691de8949e8ab1b81e1a9b9af3b199`

_RC3 commit:_ `7f53fe1dbdf189f014b0cd2643a996148fc5dba7`

## Files in scope

- `docs/current/RELEASE_STATUS.md` — changed: **no** 
  - before SHA-256: `ff2fc03d1e8cd3153d2e06394193f4d451c32062fdfdfe2fb867fdf9ad5c879b` 
  - after  SHA-256: `ff2fc03d1e8cd3153d2e06394193f4d451c32062fdfdfe2fb867fdf9ad5c879b`
- `docs/current/DOCS_AUTHORITY_MAP.md` — changed: **no** 
  - before SHA-256: `fe3c94f765386a5a4529c16b7349550a79befdaf68b76d90f5904838c2657459` 
  - after  SHA-256: `fe3c94f765386a5a4529c16b7349550a79befdaf68b76d90f5904838c2657459`
- `docs/current/PUBLIC_RELEASE_READINESS.md` — changed: **no** 
  - before SHA-256: `b4d5de1bca4ade75b077b45ea89ae3fe7d335a680a54999719121f25370fa9bd` 
  - after  SHA-256: `b4d5de1bca4ade75b077b45ea89ae3fe7d335a680a54999719121f25370fa9bd`
- `docs/current/SETUP_GAPS.md` — changed: **no** 
  - before SHA-256: `f549e0df9e377498187ad5810c22ef3c3c58e45483fa24d98b7d05a69d92dba6` 
  - after  SHA-256: `f549e0df9e377498187ad5810c22ef3c3c58e45483fa24d98b7d05a69d92dba6`

## How to roll back

```bash
# inspect what would happen (no writes)
./eval/secretary_current_refresh/snapshots/20260503_055510/rollback.sh --check

# perform rollback
./eval/secretary_current_refresh/snapshots/20260503_055510/rollback.sh
```

The rollback restores the four `docs/current/*.md` files from the `before/` directory captured by this snapshot. **No `git` commands are run.** T should review the resulting working tree with `git diff docs/current/` and decide whether to commit, revert further, or leave as-is.
