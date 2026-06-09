# Quickstart — MMV Current Workspace

A five-minute first-run path. For deeper detail, see
[README.md](README.md), [docs/current/DOCS_AUTHORITY_MAP.md](docs/current/DOCS_AUTHORITY_MAP.md),
[prompts/l0_integrated_v8_4.md](prompts/l0_integrated_v8_4.md), and
`CLAUDE.md`.

Current protocol authority is **L0 v8.4** (current behavior is the
**v8.4.1** reason-aware abstain point-revision, which retains the v8.4
file names). The older v0.1-rc1 quickstart measurements below remain
useful install baselines, but current L0 / release-status reading is
governed by the v8.4 / v8.4.1 and RC3.3 documents.

## 1. Requirements

Minimum:

- **Python 3.13+** (the project pins `requires-python = ">=3.13"`).
- **Disk**: ~2 GB for source + Python deps.
  - Add **~2 GB more** for the ME5 multilingual-large model (downloaded
    on first run, cached under `HF_HOME`).
  - Wikipedia / ISM-corpus / FAISS indices add up to several GB *if you
    rebuild them locally* — these are **not** committed; see §6.
- **OS**: Linux preferred (developed on Ubuntu 24.04). Other POSIX
  systems should work but are not the reference platform.
- **Inference backend**: Ollama with `qwen3.5:9b` (reference). CPU is
  fine for ME5 embeddings; a single GPU slot is preferred for FAISS
  index rebuilds.

Optional (enabled by populating `.env` keys):

- **Brave Search API** — for freshness-sensitive verify-route queries.
- **Groq API** — for the Self-Governance Protocol supervisor and the
  RL eval harness's LLM judge. Sign up at <https://console.groq.com/>.
- **Kiwix ZIM** — local-Wikipedia retrieval fallback.

## 2. Configure environment

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

Fill in the keys you actually have. **All keys are optional**; the
runtime starts without external API access (it just won't fire the
network-bound paths). Empty placeholder values in `.env.example` are
the public template.

`.env` is gitignored — never commit it. `.env.example` is the only
file in this family that ships in the repo.

## 3. Install

There are two ways to install:

### Option A — Interactive installer (recommended for first-time users)

```bash
python3.13 install.py
```

The installer is interactive and confirms each step. It can skip
optional components (Ollama, Brave key, Kiwix). See the script header
for the full step list.

### Option B — Plain pip / venv

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -e .
# Optional dev tooling: pip install -e .[dev]
# Optional Gradio UI:   pip install -e .[ui]
```

`pyproject.toml` lists the runtime dependencies (FAISS-CPU,
sentence-transformers, transformers, requests, FastAPI, etc.). The
list is intentionally unpinned so environment-level resolution can
take over.

## 4. First run

A minimal headless smoke (does not require API keys):

```bash
python -c "
from src.kernel.routing_engine import RoutingEngine
print('routing engine importable: ok')
"
```

To run the Gradio UI (requires `pip install -e .[ui]`):

```bash
python src/ui/app.py
# Open http://localhost:7860
```

To exercise the full Answer-Entitlement loop you need Ollama running
locally with `qwen3.5:9b` available:

```bash
# in another terminal
ollama serve
ollama pull qwen3.5:9b
# then start the UI as above
```

> ⚠️ **`qwen3.5:9b` — thinking mode must stay off.** Ollama builds after
> March 2026 enable thinking mode by default. The MMV `OllamaAdapter`
> already calls `api/generate` with `"think": false`, so a stock install
> behaves correctly. If you instead see **blank assistant responses**
> (empty `response`, with the model's text landing in a `reasoning` /
> `thinking` field), thinking mode has leaked back on — confirm the
> adapter still sends `"think": false`, or pin an Ollama build that
> respects it. Full detail: `CLAUDE.md` → "qwen3.5:9b critical note".

## 5. Run the test suite

```bash
pytest tests/ -q
```

RC3.3 workspace baseline (2026-05-31, `pytest -q tests/`):

```
1092 passed, 36 skipped, 3 xfailed, 0 failed
```

If you want a fast subset, target a single area:

```bash
pytest tests/test_routing_engine.py -q
```

The full suite includes some tests that hit the local Ollama / FAISS /
ME5 stack; those are skipped if the dependency isn't available.

## 6. FAISS / ME5 indices and the ISM corpus

The repo **does not** ship the large generated artifacts:

| Artifact | Size (typical) | Distribution |
|---|---|---|
| `data/pattern_library/index.faiss` | ~5 MB | rebuild locally — see below |
| `data/raf/ism_index.faiss` | ~150 MB | rebuild locally |
| `data/raf/qk_index.faiss` | ~150 MB | rebuild locally |
| `data/raf/teacher_data_raw.jsonl` (ISM corpus) | ~24 MB / 36,282 lines | distribution decision pending; see policy doc |
| Wikipedia FAISS index + chunks (`Wiki/*`) | ~1.74 GB (4 files) | **HuggingFace** — fetched by `scripts/fetch_wiki_index.py` |
| Kiwix ZIM (`~/デスクトップ/mobius_ai/kiwix/*.zim`) | ~12 GB | third-party; obtain from kiwix.org |

The full distribution policy is recorded in
[docs/INDEX_DISTRIBUTION_POLICY.md](docs/INDEX_DISTRIBUTION_POLICY.md) (FAISS / ME5) and
[docs/ISM_CORPUS_DISTRIBUTION_POLICY.md](docs/ISM_CORPUS_DISTRIBUTION_POLICY.md) (ISM corpus).

### Wikipedia / Box W index — fetch from HuggingFace

The Box W path expects the four ME5 artifacts under `Wiki/`. They live
on a HuggingFace dataset repo (default:
`huggingface.co/datasets/moebiusT7/mmv-wiki-index`) and are pulled by a
single script:

```bash
# Dry-run (resolves URL, shows plan, no download)
python scripts/fetch_wiki_index.py --dry-run

# Real fetch (~1.74 GB total; resumable; verifies SHA256 per file)
python scripts/fetch_wiki_index.py

# Override source (e.g. private mirror)
python scripts/fetch_wiki_index.py --source-url https://my-mirror.example.com/wiki --kind http_base
```

Re-running the script is idempotent: files that already exist with the
right SHA256 are skipped. Mirror configuration (URL, revision, file
list, SHAs) lives in [`config/wiki_index_source.yaml`](config/wiki_index_source.yaml).

### Release lines — choose your model path

```bash
# Inspect the active release pointer (default = Large)
python -m addons.secretary version

# Switch the active runtime to Small (local qwen3.5:9b via Ollama)
python -m addons.secretary version \
  --release_pointer_path operate-fr-bench/releases/small/current.yaml

# Switch to Medium (local gemma4:12b via Ollama)
python -m addons.secretary version \
  --release_pointer_path operate-fr-bench/releases/medium/current.yaml
```

Small requires `ollama pull qwen3.5:9b` (single 8 GB GPU is enough).
Medium requires `ollama pull gemma4:12b` (dense 11.9B; above the 8 GB
Small target — see the Medium freeze note for the measured hardware
profile). Large requires a Groq
API key in `.env` (`GROQ_API_KEY=…`, sign up at
<https://console.groq.com/>); no local model pull is needed for that line.

### Pattern Library FAISS rebuild

Quick rebuild (CPU; takes seconds for the 1,252-vector v0.1-rc1
library):

```bash
python -m scripts.build_pattern_index
# Writes:
#   data/pattern_library/index.faiss
#   data/pattern_library/index_metadata.jsonl
```

ISM / QK index rebuilds are larger operations
(see CLAUDE.md and the index distribution policy).

### Hugging Face cache

ME5 (`intfloat/multilingual-e5-large`) downloads on first encoder use.
Set `HF_HOME` in `.env` or as an env var to control where it lands:

```bash
export HF_HOME=$HOME/.cache/huggingface
```

## 7. Sanity check after install

A 30-second post-install verification:

```bash
# repo state
git rev-parse HEAD
git tag --list "mmv_core_v0_1_rc1*" "phase4_close*"

# Pattern Library counts
python -c "
from pathlib import Path
import json
INACTIVE = {'deprecation_candidate', 'deprecated', 'under_review'}
active = quarantined = 0
for jsonl in sorted(Path('config/pattern_library').glob('*.jsonl')):
    if jsonl.name.startswith('_'): continue
    for line in jsonl.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        obj = json.loads(line)
        status = obj.get('lifecycle', {}).get('audit_status', 'active')
        if status in INACTIVE: quarantined += 1
        else: active += 1
print(f'Pattern Library: {active} active / {quarantined} quarantined (expect 139 / 26)')
"

# Golden set sizes
wc -l tests/golden_set/long_tail_v1.jsonl tests/golden_set/pattern_library_golden_set_v1.jsonl
# Expect 505 / 200
```

If those four numbers (HEAD existence, 139/26, 505, 200) check out, the
install is consistent with the historical v0.1-rc1 baseline. For current
release authority, also confirm that
`docs/current/DOCS_AUTHORITY_MAP.md` points to L0 v8.4 and the RC3.3
release pointers.

## 8. What if something goes wrong

- **`ModuleNotFoundError: faiss`** — the `faiss-cpu` wheel didn't
  install. Try `pip install faiss-cpu` directly; a small subset of
  Linux distros need a system-level `libgomp1`.
- **`OSError: ME5 model could not be downloaded`** — check internet
  reachability and disk space under `HF_HOME`.
- **`Connection refused` against Ollama** — the daemon isn't running.
  `ollama serve` in another terminal, then `ollama pull qwen3.5:9b`.
- **Blank / empty responses from `qwen3.5:9b`** — Ollama thinking mode
  is on. The runtime sends `"think": false` on `api/generate`; if you
  have modified the adapter, or use a post-March-2026 Ollama build that
  re-enables thinking, the `response` field comes back empty while the
  generated text lands in a `reasoning` field. Ensure `"think": false`
  is set on the `api/generate` payload. See `CLAUDE.md` →
  "qwen3.5:9b critical note".
- **Pytest fails on a B15 latency assertion** — that test measures
  wall-clock latency and can be flaky under concurrent load. Re-run
  in isolation: `pytest tests/test_phase_c_eval.py::TestB15::test_b15_latency`.
- **`.env` not picked up** — confirm `python-dotenv` is installed
  (`pip install python-dotenv`) and that `.env` is in the repo root.

For deeper debugging, see `CLAUDE.md` (operating manual) and the
specific subsystem docs in `docs/`.
