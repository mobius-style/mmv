# Rollback Instructions — pre_stage_abc_20260424_bedtime

Created: 2026-04-24 (bedtime backup before Stage A/B/C autonomous run)
Baseline state: commit `415e2d6`, pytest 2090 passed, Evolution Log 14 entries

## Backup locations

| Artifact | Path |
|---|---|
| Git tag | `pre_stage_abc_20260424_bedtime` |
| Working-tree snapshot | `$HOME/デスクトップ/mobius_ai/MOBIUS_MMV_backup_20260424_bedtime` (~53 GB; Wiki indexes excluded, rebuildable) |
| Source-file MD5 hashes | `~/MOBIUS_MMV_pre_stage_abc_hashes.txt` (304 files) |
| Evolution Log MD5 | `~/MOBIUS_MMV_pre_stage_abc_evolog_hash.txt` (`349d3861aa0cc80102e5bf6bf4bf718c`) |

## Full rollback (完全に戻す)

```bash
cd ~/デスクトップ/mobius_ai/MOBIUS_MMV

# 1. Working tree 一時保存
git stash save "emergency_stash_$(date +%s)"

# 2. Git tag 時点に戻る
git checkout pre_stage_abc_20260424_bedtime
git checkout -b rollback_from_stage_abc_$(date +%s)

# 3. data/ 等 gitignored の restore (選択的)
rsync -a $HOME/デスクトップ/mobius_ai/MOBIUS_MMV_backup_20260424_bedtime/data/ \
  ~/デスクトップ/mobius_ai/MOBIUS_MMV/data/

# 4. Verify
git log --oneline -1          # 415e2d6 が表示されるはず
md5sum data/supervisor/evolution_log.jsonl  # 349d3861aa0cc80102e5bf6bf4bf718c
~/デスクトップ/mobius_ai/venv313/bin/pytest --tb=no tests/ 2>&1 | tail -1
#   → 2090 passed, 1 skipped, 3 xfailed
```

## Partial rollback

Stage A/B/C で追加された commit を個別に revert:

```bash
git log --oneline pre_stage_abc_20260424_bedtime..HEAD
# 戻したい commit を選んで
git revert <unwanted_commit_sha>
```

## File-level restore

```bash
# 個別 file を backup から戻す
cp "$HOME/デスクトップ/mobius_ai/MOBIUS_MMV_backup_20260424_bedtime/<path>" \
   ~/デスクトップ/mobius_ai/MOBIUS_MMV/<path>
```

## Evolution Log append-only verification

Stage A/B/C 完了後 Evolution Log が 14 entries byte-unchanged かを確認:

```bash
head -n 14 ~/デスクトップ/mobius_ai/MOBIUS_MMV/data/supervisor/evolution_log.jsonl | md5sum
# → 349d3861aa0cc80102e5bf6bf4bf718c  (必ずこの hash)
```

一致しなければ Constitutional Invariant 4 違反 — 即 full rollback。

## 注意

- backup フォルダは `--exclude='Wiki/wiki_chunks_clean.jsonl.gz'` 等で Wiki index を除外(5.5M vectors, 再生成可能)
- `venv313/` も除外。仮想環境は `mobius` alias で再構築可
- `.git/objects/pack` 除外は reflog 一部の履歴を失う可能性あり — 通常 rollback には影響なし
