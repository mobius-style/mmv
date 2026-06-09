# MOBIUS MMV — Public Release Procedure

**Audience**: project maintainer pushing the L/M/S release line to a
public GitHub mirror and offloading heavy data to HuggingFace.
**Owner**: Taiko Toeda / MOBIUS LLC.
**Last reviewed**: 2026-05-26.

This is the operating procedure produced by the 2026-05-26 packaging
pass. It assumes the workspace is already in the state landed by that
pass: Medium label aligned to RC3.3, `.gitignore` extended for
release-staging dirs, `scripts/fetch_wiki_index.py` + config in place,
and HF dataset README template under `docs/`.

The procedure has four phases:
0. **Pre-flight checks** (≈ 5 min)
1. **HuggingFace dataset publish** (one-time, ≈ 30–60 min for upload)
2. **GitHub repo publish** (≈ 10 min)
3. **Post-publish verification** (≈ 10 min on a fresh clone)

> The whole flow assumes you are publishing **one GitHub repo** with
> three release pointers (L/M/S), and **one HF dataset repo** holding
> the Wikipedia / Box W ME5 index. That shape was decided 2026-05-26
> per the user's "1リポ + 3 release pointer" answer.

---

## Phase 0 — Pre-flight checks

Run these from the repo root. None of them push anything.

### 0.1 Confirm release pointers exist and agree

```bash
for size in large medium small; do
  echo "=== $size ==="
  cat operate-fr-bench/releases/$size/current.yaml
done
```

Expected: L = `MMV-L-RC3.3`, M = `MMV-M-RC3.3`, S = `MMV-S-RC3.3`. If
M still reads `RC0.1`, the version-bump step from the 2026-05-26 pass
was not applied — repeat it before continuing.

### 0.2 Confirm `.gitignore` excludes the local-only dirs

```bash
git check-ignore -v Public/ L08.4/ MOBIUS_L08.4/ spikes/ bench/ corpus/ reports/ .codex/ Wiki/ data/
```

Every line should print a `.gitignore:<line>:<pattern>` match. If any
line prints nothing, that directory will leak into the public push.

### 0.3 Confirm the fetch script's planning step works against local Wiki/

```bash
python scripts/fetch_wiki_index.py --dry-run
```

Expected `Summary: downloaded=0, skipped=5, required-failures=0`. If
any SHA mismatch is reported, your local `Wiki/` was rebuilt with
different parameters than the config records — regenerate the SHAs in
`config/wiki_index_source.yaml` from the current files before
continuing (otherwise installers will fail verification against your
HF mirror):

```bash
sha256sum Wiki/wiki_index_ivfpq_me5.faiss Wiki/wiki_chunks_clean.jsonl.gz \
          Wiki/line_offsets.npy Wiki/line_offsets.gzidx Wiki/wiki_manifest.json
```

### 0.4 Confirm test suite is green

```bash
pytest tests/ -q 2>&1 | tail -5
```

CLAUDE.md invariant: `0 failed` with `~3 xfailed`. If anything is red,
stop — do not publish.

### 0.5 Inspect what's about to be committed

```bash
# What's tracked + dirty + new (excluding ignored)
git status --short
# What untracked files would land if you `git add .` right now
git status --short --untracked-files=all | grep '^??'
```

Triage every `??` entry. The 2026-05-26 packaging pass left these
expected categories of untracked content:

- `operate-fr-bench/` — 199 staging files. **Most must be added**:
  `README.md`, `LICENSE`, `CITATION.cff`, `NON_ASSERTION_COVENANT.md`,
  `pyproject.toml`, `configs/`, `docs/`, `harness/`, `scripts/`,
  `releases/medium/`, `releases/small/`. Skip: `backups/`, `reports/`,
  `logs/`, `tests/` (private eval data). See §2.2.
- New `config/wiki_index_source.yaml`, `scripts/fetch_wiki_index.py`,
  `docs/HF_WIKI_DATASET_README_TEMPLATE.md`,
  `docs/PUBLIC_RELEASE_PROCEDURE.md` (this file),
  `operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md` — **all add**.
- Anything under the dirs you ignored in §0.2 — `??` will not show them.

---

## Phase 1 — HuggingFace dataset publish

The HF dataset repo holds the ~1.74 GB Wikipedia / Box W ME5 artifact
set. The GitHub repo holds only the fetch script + config that points
at it.

### 1.1 Create the HF dataset repo

On <https://huggingface.co/new-dataset>:

- Owner: `moebiusT7`
- Repo name: `mmv-wiki-index` (or override; if you change it, also
  edit `config/wiki_index_source.yaml`'s `base_url`)
- License: `cc-by-sa-4.0`
- Visibility: Public

### 1.2 Authenticate the HF CLI

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli login          # paste a write-scope token
huggingface-cli whoami         # confirm
```

### 1.3 Upload the 5 files

From the MMV repo root:

```bash
huggingface-cli upload-large-folder \
  moebiusT7/mmv-wiki-index \
  Wiki/ \
  --repo-type=dataset \
  --include "wiki_index_ivfpq_me5.faiss" \
  --include "wiki_chunks_clean.jsonl.gz" \
  --include "line_offsets.npy" \
  --include "line_offsets.gzidx" \
  --include "wiki_manifest.json"
```

The upload is multi-part and resumable. Expect 30–60 minutes on a
typical home connection for ~1.74 GB.

### 1.4 Upload the dataset README

The README content lives in
[`docs/HF_WIKI_DATASET_README_TEMPLATE.md`](HF_WIKI_DATASET_README_TEMPLATE.md).
Copy the block between the two horizontal-rule lines into a local
`HF_README.md` (or just split the template file), then:

```bash
huggingface-cli upload moebiusT7/mmv-wiki-index HF_README.md README.md \
  --repo-type=dataset
```

Then check the rendered README on
<https://huggingface.co/datasets/moebiusT7/mmv-wiki-index>.

### 1.5 Pin a revision (optional, recommended)

If you want reproducible installs across HF dataset edits:

```bash
# Tag a stable revision
huggingface-cli repo tag moebiusT7/mmv-wiki-index v2026-04-17-me5 --repo-type=dataset
```

Then in `config/wiki_index_source.yaml`, change:

```yaml
source:
  revision: v2026-04-17-me5    # was: main
```

This is one git commit on the MMV side.

### 1.6 Smoke-test the fetch path from outside

Delete one local file and re-fetch from HF to prove the URL really
works (you can re-fetch with `--force` after to put it back):

```bash
mv Wiki/wiki_manifest.json /tmp/  # tiny file, fastest to round-trip
python scripts/fetch_wiki_index.py
mv /tmp/wiki_manifest.json Wiki/  # restore (or leave the fresh copy)
```

Expected: `downloaded=1, skipped=4, required-failures=0`.

---

## Phase 2 — GitHub repo publish

### 2.1 Decide the public remote URL

The current remote is `https://github.com/happy-HHH/mobius-mmv.git`
(personal account). The README/CLAUDE.md trace history also references
`mobius-llc/MOBIUS_MMV`. Pick one and stay consistent:

- **Option A**: keep `happy-HHH/mobius-mmv` (no change).
- **Option B**: create `mobius-llc/MOBIUS_MMV` on GitHub, then:

  ```bash
  git remote set-url origin https://github.com/mobius-llc/MOBIUS_MMV.git
  ```

  If you go with B, also edit the `git clone` line in `README.md`
  (currently rewritten to `happy-HHH/mobius-mmv` in the 2026-05-26
  pass — bring it back to `mobius-llc/MOBIUS_MMV` to match the new
  remote).

### 2.2 Stage operate-fr-bench/ selectively

`operate-fr-bench/` is mostly untracked but contains the L/M/S
pointers and harness code that the runtime depends on. Add only what's
publication-clean:

```bash
git add \
  operate-fr-bench/README.md \
  operate-fr-bench/LICENSE \
  operate-fr-bench/CITATION.cff \
  operate-fr-bench/NON_ASSERTION_COVENANT.md \
  operate-fr-bench/pyproject.toml \
  operate-fr-bench/configs/ \
  operate-fr-bench/docs/ \
  operate-fr-bench/harness/ \
  operate-fr-bench/scripts/ \
  operate-fr-bench/releases/

# Inspect before commit
git status --short operate-fr-bench/
```

Explicitly skip `operate-fr-bench/backups/`, `operate-fr-bench/logs/`,
`operate-fr-bench/reports/`, `operate-fr-bench/tests/` unless you've
audited them for privacy. If you want to ship empty-but-present dirs,
add a `.gitkeep` rather than the full content.

### 2.3 Stage the new release-packaging files

```bash
git add \
  .gitignore \
  README.md \
  QUICKSTART.md \
  config/wiki_index_source.yaml \
  scripts/fetch_wiki_index.py \
  docs/HF_WIKI_DATASET_README_TEMPLATE.md \
  docs/PUBLIC_RELEASE_PROCEDURE.md
```

If the Medium freeze-note rename landed but wasn't tracked:

```bash
git add operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md
# If the old RC0_1 file was tracked, git will pick up the deletion too;
# check with: git status --short operate-fr-bench/docs/
```

### 2.4 Commit and push

```bash
git status --short                 # final review
git diff --staged | wc -l          # size of the diff that will land
git commit -m "feat(release): publish-ready MMV-L/M/S RC3.3 (HF wiki offload)"
git push origin main               # or your release branch
```

If `git push` is the first push to a fresh `mobius-llc` repo, prefix
with `git push -u origin main`.

### 2.5 Tag the three release lines

```bash
git tag -a mmv-large-rc3.3-temporal-governance-20260516 -m "MMV-L-RC3.3"
git tag -a mmv-medium-rc3.3-20260517                    -m "MMV-M-RC3.3"
git tag -a mmv-small-rc3.3-routing-stabilization-20260516 -m "MMV-S-RC3.3"
git push origin --tags
```

The Large/Small tag names come from the existing freeze notes'
"Suggested tag" rows; the Medium tag follows the same pattern with the
new RC3.3 label.

### 2.6 (Optional) Cut GitHub Releases per tag

On GitHub, create a Release per tag and attach the freeze note as the
release notes body. Bodies live at:

- L: `operate-fr-bench/docs/MMV_Large_RC3_3_FREEZE_NOTE.md`
- M: `operate-fr-bench/docs/MMV_Medium_RC3_3_FREEZE_NOTE.md`
- S: `operate-fr-bench/docs/MMV_Small_RC3_3_FREEZE_NOTE.md`

(`gh release create <tag> --notes-file <path>` from the CLI.)

---

## Phase 3 — Post-publish verification

Do this on a **fresh clone** in a scratch directory — it proves the
public path works for a third party.

```bash
cd /tmp && rm -rf mmv-verify && git clone https://github.com/<OWNER>/<REPO>.git mmv-verify
cd mmv-verify
python3.13 -m venv venv && source venv/bin/activate
pip install -e .
python scripts/fetch_wiki_index.py
pytest tests/ -q 2>&1 | tail -5
```

Pass criteria:

- Clone is under ~80 MB (no large binaries leaked).
- `fetch_wiki_index.py` ends with `downloaded=4` (or `5`, with the
  manifest) and `required-failures=0`.
- Test suite reports the same `passed / xfailed / failed` numbers as
  your dev workspace (CLAUDE.md invariant: `0 failed`).
- Each release pointer is readable:

  ```bash
  for size in large medium small; do
    python -m addons.secretary version \
      --release_pointer_path operate-fr-bench/releases/$size/current.yaml
  done
  ```

Then exercise one end-to-end run per available model backend. If you
have Ollama locally:

```bash
ollama pull qwen3.5:9b
# Small-line headless smoke (or your preferred entrypoint)
```

If Groq is set up:

```bash
export GROQ_API_KEY=…
# Large-line headless smoke
```

---

## Failure-mode quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| `fetch_wiki_index.py` says `HTTP 404` | HF repo wrong, files not yet uploaded, or `revision` doesn't exist | Re-check repo name and revision in `config/wiki_index_source.yaml`; confirm files on HF web UI |
| `sha256 mismatch after download` | HF copy differs from the SHAs in config | Either re-upload from a clean local `Wiki/`, or regenerate SHAs with `sha256sum` and commit the new config |
| `fetch_wiki_index.py` says network error mid-download | Connection drop | Re-run; the script writes to `.partial`, so a fresh attempt restarts the failed file |
| Fresh clone is hundreds of MB | A previously-tracked large file was committed before `.gitignore` caught it | Check `git ls-files | xargs -I{} du -h {} | sort -hr | head` ; if needed, BFG / `git filter-repo` |
| `git status` shows new files under `Public/` after pull | `Public/` somehow not ignored | Re-run §0.2; check the project-level vs global ignore precedence |
| Medium pointer still says `MMV-M-RC0.1` after push | The 2026-05-26 version bump wasn't committed | `git log -- operate-fr-bench/releases/medium/current.yaml`; if absent, re-apply and commit |

---

## What this procedure does NOT cover

- Patent / counsel gate (CLAUDE.md "Public AGPL release remains T-gated").
  Confirm this is cleared **before** running Phase 2.
- Zenodo deposit of the `Public/` tree (separate publication path; the
  `Public/` tree is intentionally excluded from the GitHub mirror).
- Ollama model uploads. Ollama models are pulled by end users via
  `ollama pull <name>`; the MMV repo does not redistribute them.
- Renaming the GitHub repo or migrating commit history between owners
  (a one-time `git remote set-url` is enough for going forward).
