# Library Inspector — User Guide

The Library Inspector is a local-first read-mostly Web UI over the
MOBIUS Pattern Library. Phase 1 default: bind `127.0.0.1:5000`, no
authentication, PII redaction OFF. T's monthly review of pending
deletion proposals is the only out-of-band coordination point.

## Launch

```bash
# From the MOBIUS_MMV repo root, with venv313 active
python -m src.ui.library_inspector.app
```

Optional flags:

```
--port N        Listen port (default 5000)
--public        Bind 0.0.0.0 (Phase 3+ opt-in; HTTPS reverse proxy
                required, prints a warning at boot)
--config-dir    Override config/pattern_library/ location
```

For Phase 1 you can add a shell alias to your own `~/.bashrc`:

```bash
alias mobius_lib='cd ~/デスクトップ/mobius_ai/MOBIUS_MMV && source ~/デスクトップ/mobius_ai/venv313/bin/activate && python -m src.ui.library_inspector.app'
```

The inspector is intentionally NOT auto-installed into anyone's shell
rc by the project — it touches user files.

## Pages

### `/` — Browse

Topic-grouped tables of patterns. Per-row: id, intent, hit_count,
last_hit, audit_status, origin. Sort by id / hit_count / last_hit /
audit_status. Filter by audit_status / origin_type via the form at the
top. Click any pattern row to open its detail page.

The header shows total / active / deprecated / pending-proposal counts.

### `/pattern/<id>` — Detail

Full schema render for one pattern: examples, negative examples,
concept references, route configuration, cross-lingual test queries,
lifecycle metadata, lifecycle history (chronological), origin info.
Action links: **Run cross-lingual test** → `/verify/<id>`,
**Propose deletion** → `/propose/<id>`.

### `/search` — Search

Two modes selected by the dropdown:

- **text** (default, instant) — substring scan over id / intent /
  topic / examples / negatives / tags
- **semantic (ME5)** — lazy-loads the multilingual-e5-large model
  on first call (~5 s). Encodes the query with the "query: " prefix,
  runs FAISS top-K=10, max-pools to patterns, returns ranked results
  with cosine scores

### `/trace` — Routing Traces

Latest 50 traces by default (filterable up to 500 via `?n=...`). Each
trace shows the timestamp, query, matched pattern (clickable), score,
confidence, and final_route. Filter by matched pattern id, topic, or
date range.

To populate the trace directory:

```bash
export MOBIUS_PATTERN_LIBRARY=1
# then run any code that constructs a RoutingEngine
```

Every `RoutingEngine.evaluate()` call writes one trace JSONL under
`data/pattern_library/traces/YYYY-MM-DD/`. Phase 1 is advisory-only:
the trace is recorded but the routing decision itself is unchanged
(legacy regex still wins).

### `/verify/<id>` — Cross-Lingual Verification

GET shows the stored test queries (lang, query, expected_match,
min_cosine). POST runs each query through ME5 + FAISS, compares the
top match to the pattern, and returns a per-query pass/fail row plus
an overall pass-rate badge. Lazy-loads ME5 on first run; subsequent
runs reuse the loaded model.

This view is the right place to validate that a freshly authored
pattern's negative_examples and cross_lingual queries actually
discriminate as intended.

### `/audit` — Audit Log

Library health dashboard for T's monthly review:

- Total / active / deprecated / pending-proposal counters
- Recent trace count (200-cap)
- Pending deletion proposals (one row per proposal across all patterns)
- Deprecation candidates (patterns with `audit_status =
  "deprecation_candidate"`)
- Recent lifecycle events timeline (last 50, newest first)

### `/propose/<id>` — Propose Deletion

Form with proposer (pseudonym, optional — empty → "anonymous") and
reason (5-1000 characters). On submit:

1. `DeletionManager.propose()` validates input
2. Generates `proposal_id = del_YYYYMMDD_HHMMSS_<hex2>`
3. Appends `DeletionProposal(status="pending")` to
   `pattern.lifecycle.deletion_proposals`
4. Sets `pattern.lifecycle.audit_status = "user_deletion_proposed"`
5. Appends `LifecycleEvent(event="deletion_proposed")` to
   `pattern.lifecycle.history`
6. Atomically rewrites the source `config/pattern_library/<topic>.jsonl`
7. Appends a one-line audit record to
   `data/pattern_library/audit_log/proposals.jsonl`

Rate limit: **5 proposals/day per IP** (Flask-Limiter, in-memory).

T's monthly review is out-of-band: read `proposals.jsonl`, decide
approve / reject, edit the relevant pattern's lifecycle directly (or
via a future tool). Approved proposals set `pattern.deprecated = true`
and the index can be rebuilt.

### `/pattern/new` — Authoring form (NEW Phase 2 Commit 21)

T-only authoring form for creating new patterns directly via the
Web UI. Auth: HTTP Basic with SHA-256 hashed password from
`MOBIUS_LIB_AUTHOR_PASSWORD_HASH` env var. When env unset, the form
returns 403 (disabled by default — T enables locally only).

```bash
# Enable form locally
export MOBIUS_LIB_AUTHOR_PASSWORD_HASH=$(echo -n "$YOUR_PASSWORD" | sha256sum | head -c 64)
python -m src.ui.library_inspector.app
# Visit http://127.0.0.1:5000/pattern/new
# Username: anything (ignored), password: $YOUR_PASSWORD
```

Form fields:
- id (regex `pat_[a-z_]+_NNN`)
- topic (dropdown: existing topics)
- intent (free-text)
- examples textarea (≥ 5 lines)
- negative_examples textarea
- primary_box (dropdown: 9-box namespace)
- synthesis_mode (free-text)
- 6 cross-lingual query rows (lang / query / match / min_cosine);
  Pydantic enforces ≥ 2 ja + ≥ 2 zh

On submit:
1. Pydantic validates the full Pattern → 422 with inline error if invalid
2. Pre-check rejects duplicate IDs across the entire library → 422
3. Atomic JSONL append to `config/pattern_library/<topic>.jsonl`
4. LibraryReader reload (so subsequent UI views see the new pattern)
5. Redirect to `/pattern/<id>`

The form does NOT trigger automatic FAISS index rebuild. T should
run `python scripts/build_pattern_index.py` manually to make the
new pattern discoverable in `/search` and `/verify`.

### `/audit` dashboard (EXPANDED Phase 2 Commit 22)

Beyond the original Phase 1 layout, the dashboard now shows:

- **Trace metrics**: aggregated from latest 200 traces (library-match
  rate, by-topic distribution, by-confidence distribution)
- **Origin breakdown**: count of patterns by origin.type
  (manual / forensic / autogen / secretary / user_proposal)
- **Hit-count histogram**: buckets patterns by lifecycle.hit_count
  (0 / 1-9 / 10-99 / 100-999 / 1000+) — empty until Phase 3
  hit-counting wires runtime telemetry
- **Library size growth**: cumulative pattern count by creation
  date from lifecycle.history events
- **Auto-gen batch summary**: aggregated from
  `data/pattern_library/audit_log/autogen_*.summary.json` —
  batch_id, started_at, patterns count, examples added
- **Paginated lifecycle timeline**: 100 events/page (was 50 in Phase 1)

## Privacy and security

- Phase 1 default: localhost only. No authentication.
- Trace and proposal content is NOT redacted in Phase 1 — the local
  user is presumed to be the data owner.
- Public mode (`--public`) is gated behind opt-in and prints a warning.
  Spec 5.7.6.2 calls for HTTPS reverse proxy, rate limit hardening,
  CAPTCHA, and PII redaction before exposing publicly.

## Troubleshooting

- **"Index missing" on /verify**: run `python scripts/build_pattern_index.py`
- **Empty /trace page**: traces only populate when
  `MOBIUS_PATTERN_LIBRARY=1` is set in the environment that constructs
  the routing engine. Phase 1 default is OFF for performance reasons
  (avoiding ME5 model load × N RoutingEngine instances).
- **Semantic search returns nothing**: ME5 is lazy-loaded on first
  semantic search; first call takes ~5 s. If the index is missing, the
  result table will be empty.
- **/propose returns 429**: rate limit hit (5/day/IP). Retry tomorrow
  or restart the process to clear the in-memory limiter.
