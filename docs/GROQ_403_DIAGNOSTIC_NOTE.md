# Groq 403 Diagnostic Note

**Date**: 2026-04-29
**Scope**: cause diagnosis only. **No repair, no rerun, no commit.**
**Anchor**: HEAD `ecf90bf` (P9 Evidence Pack v1 + judge repair pass).

> The diagnostic was deliberately read-only. No `GROQ_API_KEY` value
> (or any prefix / suffix) is included in this note. No request body
> or response that contained the key is reproduced.

## Verdict

**`CLOUDFLARE_OR_NETWORK_LIKELY`** — specifically a **Cloudflare
User-Agent fingerprint block**.

(The diagnostic script's automated classifier emitted
`MODEL_PERMISSION_OR_ACCOUNT_LIKELY` because the 403 body was
JSON-shaped, but inspection of the JSON content shows the body is a
Cloudflare-emitted JSON error referencing
`cloudflare-1xxx-errors/error-1010/`, not a Groq API-level error.
The decisive evidence is in §7 below.)

## Probes performed (read-only)

| # | Probe | Outcome | Notes |
|---|---|---|---|
| 1 | `GROQ_API_KEY` presence | **present** (loaded from `.env`); length **56**; format **gsk_…**-prefixed | Length and format-prefix consistent with current Groq API key shape; **no key chars logged**. |
| 2 | `GET /openai/v1/models` (default User-Agent) | **HTTP 403** in 0.14 s | `Server: cloudflare`, `CF-Ray: …-NRT`. JSON body has `error_code: 1010`. |
| 3 | gpt-oss-120b in models list | **could not enumerate** — `/models` itself is 403 | (Therefore "is the model in the list?" is unanswerable from the client side until the 403 clears.) |
| 4 | Chat probe `llama-3.1-8b-instant` | **HTTP 403** | Same Cloudflare-1010 body. |
| 4 | Chat probe `llama-3.3-70b-versatile` | **HTTP 403** | Same. |
| 4 | Chat probe `mixtral-8x7b-32768` | **HTTP 403** | Same. |
| 5 | Chat probe `openai/gpt-oss-120b` | **HTTP 403** | Same Cloudflare-1010 body (i.e., **not** a model-specific block). |
| 6 | 403 body classification | **Cloudflare-emitted JSON**, not Groq JSON | See §6 below. |
| 7 | Chat probe `openai/gpt-oss-120b` **with explicit User-Agent** (`Mozilla/5.0 (compatible; mmv-mmv-diagnostic/1.0)`) | **HTTP 200**, normal completion | Decisive — see §7. |

Each probe used the same `GROQ_API_KEY`; the only intentional variable
in step 7 was the `User-Agent` request header.

## §6. Body classification — why JSON ≠ "Groq API error"

All four 403 responses returned bodies that **look** like JSON but are
**Cloudflare-emitted**, not Groq-emitted. Identifying signals:

- `Server: cloudflare`
- `CF-Ray: <ray-id>-NRT`
- Body URL pointer: `https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/`
- Field `error_code: 1010`
- Phrase `"blocked access based on your browser's signature"`

Cloudflare error 1010 is documented as "Access denied based on the
client's browser signature" — i.e., a **User-Agent / TLS-fingerprint
edge block**, applied at Cloudflare's WAF layer **before** the
request reaches Groq's API tier. The presence of `application/json`
content-type is misleading because it caused the diagnostic
classifier to bucket this as "JSON-ERROR (API-level)".

## §7. Decisive evidence — User-Agent variant succeeds

Identical chat completion call to `openai/gpt-oss-120b`, sent twice
in the same diagnostic run:

| Variant | User-Agent | Status | Notes |
|---|---|---|---|
| A | (Python `urllib` default; typically `Python-urllib/3.13`) | **403** Cloudflare 1010 | Block triggered |
| B | `Mozilla/5.0 (compatible; mmv-mmv-diagnostic/1.0)` | **200** OK | Real chat completion returned, with `usage` block |

Variant B's response body opens with `{"id":"chatcmpl-…","object":"chat.completion","created":…,"model":"openai/gpt-oss-120b","choices":[…],"usage":{…}}` — i.e., a real Groq response with the actual model and token usage. **This proves the API key is valid, the account is active, and the model `openai/gpt-oss-120b` is permitted on this account.** The 403 was purely a User-Agent fingerprint block at Cloudflare's edge.

## §8. Classification (per the four required buckets)

| Bucket | Selected? | Reason |
|---|---|---|
| `SERVICE_OUTAGE_LIKELY` | no | Cloudflare returned a structured 1010 (not 502/504/521); endpoint is reachable |
| `MODEL_PERMISSION_OR_ACCOUNT_LIKELY` | no | UA-variant returned **HTTP 200** with a real completion on `openai/gpt-oss-120b`; the same key works once the UA is changed |
| `CLOUDFLARE_OR_NETWORK_LIKELY` | **yes** | All evidence points to a Cloudflare 1010 User-Agent fingerprint block; UA-variant test confirms |
| `UNKNOWN` | no | The cause is identified |

## What this means operationally (information only — no repair done)

- The Phase 5C Test 2 judge-call code path used Python `urllib` with no
  explicit `User-Agent`, so the default `Python-urllib/3.13`
  fingerprint was sent — exactly the fingerprint Cloudflare 1010 is
  rejecting on the Groq edge.
- Setting an explicit `User-Agent` header in the judge HTTP request
  causes the same key + same model + same payload to succeed.
- **No change has been made to the Test 2 / judge-repair code in this
  diagnostic pass.** The user explicitly forbade repair / rerun.

## What was *not* done (per scope)

- No fix was applied to `eval/p9_evidence_pack_v1/run_test2_raw_vs_governed.py`
  or `…/run_test2_judge_repair.py`.
- No re-run of the original Phase 5C Test 2 judge pass.
- No re-run of the judge-repair pass with corrected User-Agent.
- No modification of `src/`, `config/`, `tests/`, `data/raf/`,
  `prompts/`.
- No git commit.
- No secret value (key chars or partial) is recorded in this note or
  in `/tmp/groq_403_diag.json`.

## Recommended next step (decision is the operator's)

The cleanest minimal repair would be to add an explicit `User-Agent`
header in the small number of places that hit the Groq endpoint
directly, e.g.:

```python
headers["User-Agent"] = "mmv-mmv/0.1 (+https://mobius.style)"
```

Files that currently hit Groq directly (relevant to the judge path):

- `eval/p9_evidence_pack_v1/run_test2_raw_vs_governed.py` (`call_judge`)
- Other scripts that call Groq via `urllib` similarly may benefit
  from the same one-line addition; the project's existing
  `scripts/groq/groq_adapter.py` and the `groq` SDK based paths
  set their own User-Agent and are not affected.

Whether to apply that fix and re-run the original Groq-judge pass for
P9 cleanliness is **the operator's decision**. This note is
diagnostic only.

## Artefacts

- `/tmp/groq_403_diag.json` — full structured diagnostic output (no
  secrets). Not committed; this note is the public record.
- This file: `docs/GROQ_403_DIAGNOSTIC_NOTE.md` (read-only diagnostic
  note; not committed by the diagnostic step itself).
