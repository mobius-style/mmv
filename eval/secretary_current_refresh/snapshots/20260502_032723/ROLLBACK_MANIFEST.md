# Rollback manifest


_Snapshot timestamp:_ `20260502_032723`

_Repo HEAD at snapshot:_ `b156b4c60c493cbe9b3b0ea40d552b9c6f81a492`

_RC3 commit:_ `7f53fe1dbdf189f014b0cd2643a996148fc5dba7`

## Files in scope

- `docs/current/RELEASE_STATUS.md` — changed: **no** 
  - before SHA-256: `208060cca258dc7c3c9999204ef9b525ccbf988dbc90846929916d84d568e236` 
  - after  SHA-256: `208060cca258dc7c3c9999204ef9b525ccbf988dbc90846929916d84d568e236`
- `docs/current/DOCS_AUTHORITY_MAP.md` — changed: **no** 
  - before SHA-256: `0f2cfcce66a81ad2f55a04318238d112faf02bd39d61ad322a9bb83be71ee418` 
  - after  SHA-256: `0f2cfcce66a81ad2f55a04318238d112faf02bd39d61ad322a9bb83be71ee418`
- `docs/current/PUBLIC_RELEASE_READINESS.md` — changed: **no** 
  - before SHA-256: `5ec81ff35b5e79d161ac782e94d66c1f4c4c82a04f8b4822241e94fcddde0d92` 
  - after  SHA-256: `5ec81ff35b5e79d161ac782e94d66c1f4c4c82a04f8b4822241e94fcddde0d92`
- `docs/current/SETUP_GAPS.md` — changed: **no** 
  - before SHA-256: `e68c54814cf8ab58a0f5dc426252f96e1845158aebe00f5989609bd25fbcbed4` 
  - after  SHA-256: `e68c54814cf8ab58a0f5dc426252f96e1845158aebe00f5989609bd25fbcbed4`

## How to roll back

```bash
# inspect what would happen (no writes)
./eval/secretary_current_refresh/snapshots/20260502_032723/rollback.sh --check

# perform rollback
./eval/secretary_current_refresh/snapshots/20260502_032723/rollback.sh
```

The rollback restores the four `docs/current/*.md` files from the `before/` directory captured by this snapshot. **No `git` commands are run.** T should review the resulting working tree with `git diff docs/current/` and decide whether to commit, revert further, or leave as-is.
