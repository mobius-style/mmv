# eval/l0_compact — row-level data for the L0 Essentials compact ablation

All runs: llama.cpp `llama-server` (build cu13, 2026-09), `-c 32768 --flash-attn on
--cache-type-k q8_0 --cache-type-v q8_0 --jinja -t 8 -np 1`, requests to
`/v1/chat/completions` with `temperature 0.2, top_p 0.95, max_tokens 6000`,
seeds 7 / 101 / 202.

| model | file | placement | thinking |
|---|---|---|---|
| gemma4:26b-a4b-it-qat | ollama blob (Google QAT) | `CUDA_VISIBLE_DEVICES=0` | `--reasoning-budget 4096` |
| gemma4:31b-it-qat | ollama blob | `--tensor-split 2,1` | `--reasoning-budget 4096` |
| gpt-oss-20b | UD-Q4_K_XL | GPU0 alone | axis A `--reasoning-budget 4096`; axes B/C `--reasoning-effort low` (Harmony ignores the budget) |
| qwen3:30b-a3b | ollama blob | `--tensor-split 2,1` | `--reasoning-budget 4096` |
| Qwen3.8-27B | UD-Q6_K | `--tensor-split 2,1` | `--reasoning-budget 4096` |
| deepseek-r1:14b | ollama blob | GPU0 alone | `--reasoning-budget 4096` (note: capping made this model fabricate where uncapped it declined) |

## Directories

| dir | what |
|---|---|
| `agent_ablation/` | gemma4:26b, 6 tool-loop probes × 6 system layers (none / full L0 / core clauses / irreversibility sentence / ask plain / ask route) |
| `agent_transfer/` | gpt-oss-20b, qwen3:30b-a3b: 2 decisive probes × 4 layers |
| `premise/` | 4 false-premise questions × 4 layers, three models |
| `compact_v1/` | compact v1 (json) and its rejected plain rewrite, both axes, three models |
| `compact_v2_rejected/` | v2 (precedence clause) against v1, five models — rejected |
| `compact_v1_1/` | v1.1 (abstain aligned to v8.4.1) against v1, axes A / B / C |
| `tasks_*.py` | the scorers, exactly as used (with their documented fixes) |
| `PREDICTIONS_*.md` | predictions written before each run, with outcomes |

Scores are keyword/regex judgements over the raw `content`; re-derive them from
the rows rather than trusting the `score` field. A row's `detail` string says
which rule fired (`asked first`, `FABRICATED`, `evasive`, `declined+educated`, …)
and, for gpt-oss, whether the text came from `content` or `reasoning_content`.

`__pycache__`, hostnames, and local paths were stripped before publishing.
