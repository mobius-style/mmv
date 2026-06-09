# HF Wikipedia / Box W Index — Upload Template

> This file is **for upload to the Hugging Face dataset repo**, not for
> the GitHub repo. Copy the YAML frontmatter + body below into the HF
> dataset's `README.md`. The GitHub-side `scripts/fetch_wiki_index.py`
> pulls the files declared in `config/wiki_index_source.yaml` from
> whichever HF dataset URL is configured (default:
> `moebiusT7/mmv-wiki-index`).

The block between the two `---` HR lines below is what should land on
HF. Edit `pretty_name`, `language` etc. as needed before pasting.

---

```markdown
---
pretty_name: "MOBIUS MMV — Wikipedia / Box W ME5 Index"
license: cc-by-sa-4.0
language:
  - en
  - ja
  - multilingual
task_categories:
  - feature-extraction
  - text-retrieval
tags:
  - faiss
  - ivfpq
  - wikipedia
  - me5
  - multilingual-e5-large
  - mobius-mmv
  - operate-fr
  - retrieval-augmented-generation
size_categories:
  - 1M<n<10M
source_datasets:
  - wikimedia/wikipedia
---

# MOBIUS MMV — Wikipedia / Box W ME5 Index

Pre-built FAISS index and chunk store for the **Box W (Wikipedia)
ME5 cross-lingual retrieval path** used by [MOBIUS MMV](https://github.com/<OWNER>/<REPO>).
This dataset is the offload target for the GitHub repo's `Wiki/`
directory: those binaries are too large to live in git, so the public
runtime expects to fetch them from here on first run.

The MMV runtime reads `config/wiki_index_source.yaml` and downloads
each file below into `Wiki/` after verifying its SHA256. See the GitHub
README for the install step:

```bash
python scripts/fetch_wiki_index.py
```

## What this is

| Property | Value |
|---|---|
| Vector count | **5,458,524** chunks |
| Embedding model | `intfloat/multilingual-e5-large` (1024-dim, CPU-friendly) |
| Index type | `IndexIVFPQ` (`nlist=4096`, `m=48`, `nbits=8`), metric: inner product |
| Recommended nprobe | 32 |
| ZIM source | `wikipedia_en_all_mini_2026-03.zim` |
| ME5 build date | 2026-04-17 |
| Cross-lingual | Yes — JP queries match EN articles directly (scores 0.77–0.78 on author's eval set) |

## Files

| File | Size | SHA256 (prefix) | Required | Role |
|---|---:|---|---|---|
| `wiki_index_ivfpq_me5.faiss` | 391.8 MiB | `06c3a2d7…` | yes | ME5 IVFPQ FAISS index |
| `wiki_chunks_clean.jsonl.gz` | 1.30 GiB | `06684522…` | yes | Cleaned chunk store backing the index |
| `line_offsets.npy` | 41.6 MiB | `9dd55e9d…` | yes | Numpy line-offset table for O(1) chunk lookup |
| `line_offsets.gzidx` | 1.2 MiB | `cfcdadbf…` | yes | gzip index for random-access reads |
| `wiki_manifest.json` | 510 B | `172018f8…` | no | Historical build manifest (informational) |

**Total**: approximately 1.74 GiB. Full SHA256 strings are in the GitHub
repo's `config/wiki_index_source.yaml`.

## How to use directly (without the runtime)

```python
import faiss, gzip, json, numpy as np
from sentence_transformers import SentenceTransformer

index = faiss.read_index("wiki_index_ivfpq_me5.faiss")
index.nprobe = 32
encoder = SentenceTransformer("intfloat/multilingual-e5-large")

q = encoder.encode(["query: 富士山の標高は？"], normalize_embeddings=True)
scores, ids = index.search(q.astype("float32"), k=8)

offsets = np.load("line_offsets.npy")
with gzip.open("wiki_chunks_clean.jsonl.gz", "rb") as fh:
    for rank, idx in enumerate(ids[0]):
        fh.seek(int(offsets[idx]))
        chunk = json.loads(fh.readline())
        print(rank, round(float(scores[0][rank]), 3), chunk["title"])
```

The ME5 model expects the `"query: "` prefix for retrieval queries and
the `"passage: "` prefix for indexed passages. The chunks were
embedded with the passage prefix at build time; do not re-embed.

## License & attribution

- **Index, chunk store, offsets**: derived from Wikipedia content.
  Distributed under **CC BY-SA 4.0**, inheriting from the upstream
  Wikipedia license. When re-distributing, preserve attribution to
  Wikipedia and link back to the source articles where possible — the
  chunks include the article `title` field for this purpose.
- **Embedding model** (`intfloat/multilingual-e5-large`): see the
  model's own license on HF; not redistributed in this dataset.
- **MOBIUS MMV runtime code** (uses these files): AGPL-3.0-or-later.
  See the GitHub repo's `LICENSE`.

## Provenance

This dataset was built from the publicly available Wikipedia ZIM
distribution (`wikipedia_en_all_mini_2026-03.zim`), chunked, cleaned,
and embedded with `intfloat/multilingual-e5-large`. The build is
deterministic given the same inputs; the SHA256 hashes above are
authoritative.

The original Stage-1/Stage-2 build (different embedding model, 384-dim
minilm) is preserved in `wiki_manifest.json` for historical reference
only; the runtime uses the ME5 1024-dim path.

## Versioning

Push a new revision when:
- The ZIM source is bumped (new Wikipedia snapshot)
- The embedding model is replaced
- The chunking strategy changes

When you do, update the GitHub-side `config/wiki_index_source.yaml`
with the new SHAs and either bump the `revision:` field or push to a
new dataset repo. Old revisions remain pullable via HF's git-LFS
history.
```

---

## Upload procedure (one-time)

After creating the HF dataset repo (e.g. `moebiusT7/mmv-wiki-index`):

```bash
# 1. Install HF CLI if needed
pip install -U "huggingface_hub[cli]"

# 2. Authenticate (writes ~/.huggingface/token)
huggingface-cli login

# 3. From the MMV repo root, push the 5 files. Use `upload-large-folder`
#    (multi-part; resumable; correct for >1 GiB files).
huggingface-cli upload-large-folder \
  moebiusT7/mmv-wiki-index \
  Wiki/ \
  --repo-type=dataset \
  --include "wiki_index_ivfpq_me5.faiss" \
  --include "wiki_chunks_clean.jsonl.gz" \
  --include "line_offsets.npy" \
  --include "line_offsets.gzidx" \
  --include "wiki_manifest.json"

# 4. Paste the README block above (between the two `---` lines) into the
#    repo's README on the HF web UI, or:
huggingface-cli upload moebiusT7/mmv-wiki-index README.md README.md \
  --repo-type=dataset
```

## Sanity check after upload

From a fresh clone (or after deleting local `Wiki/*`):

```bash
python scripts/fetch_wiki_index.py --dry-run    # confirms URL resolution
python scripts/fetch_wiki_index.py              # actual fetch + verify
```

A successful run prints `Summary: downloaded=4, skipped=0,
required-failures=0` (or `downloaded=0, skipped=4` if files already
present locally).
