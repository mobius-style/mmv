# Third-Party Licenses — MMV Core v0.1-rc1

MMV Core is licensed AGPL-3.0-or-later (see [LICENSE](LICENSE)). This
document inventories the third-party software, models, and data the
runtime depends on, with their licenses and the role they play. It is
intended to satisfy distribution attribution obligations for the
v0.1-rc1 public release and to make the dependency surface auditable.

This file is informational and does not modify or override any
upstream license. Where a discrepancy exists between this summary and
the upstream LICENSE file, the upstream LICENSE governs.

## 1. Python runtime dependencies

These are declared in `pyproject.toml`. Versions reflect the floors
specified there (the project is unpinned to allow environment-level
resolution; `pip install -e .` will resolve the exact installed
versions).

| Package | Floor | Upstream license | Role in MMV |
|---|---|---|---|
| `requests` | ≥2.31 | Apache-2.0 | HTTP client (Brave / Groq / Ollama) |
| `httpx` | ≥0.27 | BSD-3-Clause | HTTP client (async paths) |
| `python-dotenv` | ≥1.0 | BSD-3-Clause | `.env` loading |
| `faiss-cpu` | ≥1.8 | MIT | dense vector index (Pattern Library, Box W Wikipedia, ISM) |
| `sentence-transformers` | ≥2.7 | Apache-2.0 | wrapper around HF transformers for embedding pipelines |
| `transformers` | ≥4.40 | Apache-2.0 | HF transformer model loaders (used by sentence-transformers) |
| `numpy` | ≥1.26 | BSD-3-Clause | array ops underlying FAISS / embeddings |
| `langdetect` | ≥1.0.9 | Apache-2.0 | language detection (language_policy fallback) |
| `watchdog` | ≥4.0 | Apache-2.0 | filesystem watching for corpus indexing |
| `pypdf` | ≥4.0 | BSD-3-Clause | PDF text extraction (custom_rag_adapter) |
| `python-docx` | ≥1.1 | MIT | DOCX text extraction |
| `beautifulsoup4` | ≥4.12 | MIT | HTML parsing |
| `PyYAML` | ≥6.0 | MIT | YAML config (`config/pattern_library/*.yaml`, etc.) |
| `pydantic` | (transitive) | MIT | model validation (Pattern Library schema) |
| `fastapi` | ≥0.110 | MIT | OpenAI-compatible HTTP API surface (`src/app/api.py`) |
| `uvicorn` | ≥0.29 | BSD-3-Clause | ASGI server for FastAPI |
| `flask` | (used by inspector) | BSD-3-Clause | local Pattern Library Inspector (Phase 2) |

Optional / extras:

| Package | Floor | Upstream license | Role |
|---|---|---|---|
| `gradio` | ≥4.0 | Apache-2.0 | optional Gradio UI (`pip install -e .[ui]`) |
| `pytest` | ≥8.0 | MIT | test runner (dev / eval extras) |
| `pytest-cov` | ≥5.0 | MIT | coverage (dev extras) |

The transitive dependency closure (e.g., `urllib3`, `charset-normalizer`,
`tokenizers`, `safetensors`, `huggingface-hub`, `tqdm`, `regex`, `click`,
`anyio`, `starlette`) carries the standard mix of Apache-2.0 / MIT /
BSD-3-Clause licenses set by upstream. None impose obligations beyond
attribution.

## 2. Models

| Model | License | Role | Distribution |
|---|---|---|---|
| `intfloat/multilingual-e5-large` (ME5-large) | MIT | cross-lingual embedding for the Pattern Library, ISM corpus, Box W Wikipedia, and golden-set evaluation | downloaded on first use under `HF_HOME` (Hugging Face); not committed to this repo |
| `qwen3.5:9b` (recommended Ollama model) | Tongyi Qianwen LICENSE AGREEMENT (Alibaba) | answer/verify synthesis | obtained via `ollama pull qwen3.5:9b`; not committed |
| `phi4-mini` (paper baseline reference) | MIT (Microsoft) | reference baseline only; not the production path | obtained via Ollama; not committed |
| Other Ollama models (optional) | per upstream | candidate evaluation only | per user choice |

Users are responsible for accepting the model licenses at the time of
download. The MOBIUS LLC AGPL-3.0-or-later license on this repository
does not relicense any third-party model.

## 3. External APIs

These are network services the runtime can call when their respective
keys are configured in `.env`. They are **optional** — the runtime
starts without them.

| Service | Terms reference | Used for |
|---|---|---|
| Brave Search API | https://brave.com/search/api/ (Brave's API terms) | freshness-sensitive verify-route queries (Box C) |
| Groq API | https://groq.com/ (Groq's API terms) | Self-Governance Protocol supervisor; eval LLM judge |
| Ollama (local) | https://ollama.com/ (Apache-2.0 server) | local inference; the LLM endpoint behind `OLLAMA_ENDPOINT` |
| Hugging Face Hub (downloads) | https://huggingface.co/ (HF Hub terms) | model download |
| Vertex AI (stub; optional) | per Google Cloud terms | not active in v0.1-rc1; placeholder in `.env.example` |

## 4. Third-party data artifacts

These are large data sets the runtime can use; **none are bundled in
this repository**. v0.1-rc1 ships pointers and rebuild scripts, not
the data.

| Artifact | License | How to obtain |
|---|---|---|
| Wikipedia corpus / vector index (`Wiki/wiki_index_*.faiss`, `Wiki/wiki_chunks_clean.jsonl.gz`) | CC BY-SA 4.0 (Wikipedia content) | available separately on the project's HuggingFace repository per the project; or rebuild from a Wikipedia dump |
| Kiwix ZIM (e.g., `wikipedia_en_all_mini_2026-03.zim`) | CC BY-SA 4.0 (Wikipedia content) | obtain from https://kiwix.org/ — not bundled |
| ISM corpus (`data/raf/teacher_data_raw.jsonl`) | mixed; provenance varies (see distribution policy doc) | distribution decision pending — see [docs/ISM_CORPUS_DISTRIBUTION_POLICY.md](docs/ISM_CORPUS_DISTRIBUTION_POLICY.md) |
| Pre-built FAISS indices for Pattern Library / ISM / QK | derived from upstream content + ME5 embeddings | rebuild scripts ship in this repo; see [docs/INDEX_DISTRIBUTION_POLICY.md](docs/INDEX_DISTRIBUTION_POLICY.md) |

The repo's `.gitignore` excludes `*.faiss`, `*.zim`, `*.jsonl.gz`, and
`data/` so these artifacts cannot be accidentally committed.

## 5. MMV-authored content

Items authored or significantly modified for MOBIUS MMV:

| Artifact | License (MMV terms) |
|---|---|
| Source code (`src/`, `scripts/`, `tests/`, `prompts/`, `install.py`) | AGPL-3.0-or-later |
| Documentation (`README.md`, `CLAUDE.md`, `docs/*.md`, this file) | CC BY-NC-SA 4.0 |
| Pattern Library (`config/pattern_library/*.jsonl`, `config/pattern_library/*.yaml`) | CC BY-NC-SA 4.0 (data); structure is part of the AGPL-licensed runtime |
| Golden sets (`tests/golden_set/*.jsonl`) | CC BY-NC-SA 4.0 |
| Wikipedia-derived vector data, when distributed | CC BY-SA 4.0 (inherits) |

The "Wikipedia-derived data: CC BY-SA 4.0" line in the repository's
README and LICENSE governs anything we redistribute that incorporates
Wikipedia content. We do not bundle such content in v0.1-rc1, but the
license stays compatible for any future distribution channel.

## 6. Reporting attribution issues

If you believe a third-party component is missing from this list, or
the license assignment here is incorrect, please open an issue (channel
to be confirmed before public push) or email **info@mobius.style**. The
maintainers will correct attribution promptly.

This file is updated alongside dependency changes; the source of truth
for runtime imports is `pyproject.toml`.
