# Rollback manifest


_Snapshot timestamp:_ `20260516_102436`

_Repo HEAD at snapshot:_ `a382f1a9fe4ee302206aa168720eb400e3646609`

_RC3 commit:_ `7f53fe1dbdf189f014b0cd2643a996148fc5dba7`

## Files in scope

- `docs/current/RELEASE_STATUS.md` — changed: **yes** 
  - before SHA-256: `208060cca258dc7c3c9999204ef9b525ccbf988dbc90846929916d84d568e236` 
  - after  SHA-256: `79c8acc203086d65a97e721a86cbf1a74945e02391803f3fb48a5f06fa184e0f`
- `docs/current/DOCS_AUTHORITY_MAP.md` — changed: **yes** 
  - before SHA-256: `0f2cfcce66a81ad2f55a04318238d112faf02bd39d61ad322a9bb83be71ee418` 
  - after  SHA-256: `4990c2485040f4916eb07474e5e47eb7e5567223cae369b41ffd163555c0bd91`
- `docs/current/PUBLIC_RELEASE_READINESS.md` — changed: **yes** 
  - before SHA-256: `5ec81ff35b5e79d161ac782e94d66c1f4c4c82a04f8b4822241e94fcddde0d92` 
  - after  SHA-256: `576c815d1c0a0bb0969a88ba8c9b9d71cc1a11139ad0aedcf02c93419abb9b49`
- `docs/current/SETUP_GAPS.md` — changed: **yes** 
  - before SHA-256: `e68c54814cf8ab58a0f5dc426252f96e1845158aebe00f5989609bd25fbcbed4` 
  - after  SHA-256: `70dbc1d93eeb2b5d8bb030b4b59c25d11393cc834061b722ad1a2697e79572f2`

## How to roll back

```bash
# inspect what would happen (no writes)
./eval/secretary_current_refresh/snapshots/20260516_102436/rollback.sh --check

# perform rollback
./eval/secretary_current_refresh/snapshots/20260516_102436/rollback.sh
```

The rollback restores the four `docs/current/*.md` files from the `before/` directory captured by this snapshot. **No `git` commands are run.** T should review the resulting working tree with `git diff docs/current/` and decide whether to commit, revert further, or leave as-is.
