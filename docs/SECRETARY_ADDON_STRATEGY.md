# Secretary — Addon Strategy

**Status**: Strategy only. No implementation in this Phase 5A pass.
**Effective from**: 2026-04-29 freeze line.

## Premise (the policy decision this doc records)

Secretary autonomy is a flagship Phase 5+ feature, but **it does not
ship in MMV Core v0.1-rc1**. The Core is frozen at the Phase 4 closure
state for public-release preparation; Secretary work happens *above*
that frozen Core, as an addon, with explicit boundaries.

Two reasons:

1. **Public-release ergonomics.** v0.1-rc1 is a routing / governance
   runtime. Embedding an autonomous-agent layer changes the audience,
   the licensing conversation, and the threat surface. A clean Core
   ships first.
2. **Dogfooding.** Secretary should be developed *using* MMV Core
   (routing / appraisal / Pattern Library / governance), not inside
   it. This forces the Core's API surface to be honest and exposes
   integration ergonomics before external developers hit them.

## What Secretary is

A cognitive-load-reduction interface that watches the user's project
state and surfaces concise briefs:

- Reads logs (`.phase4_autodriver.log`, evolution logs, recent commits).
- Reads docs (handover docs, findings, open TODOs in markdown).
- Detects stale docs, missing markers (e.g., the
  AUTODRIVER_TRIGGER_START/END insertion that broke the b15-19 cron
  chain), leftover cron jobs, dirty working trees, drift in expected
  state.
- Produces a short brief on demand: "what changed since you last
  checked, what's broken, what's blocked."

It is *not* a full agent. It is a **secretary** — it watches and
proposes; it does not act unilaterally.

## What Secretary is not

- Not a code generator.
- Not a Phase-driver replacement (Phase 4 autodriver was a different
  artifact; that work is done).
- Not a unit-test runner replacement.
- Not a CI tool.
- Not a chatbot front-end.
- Not part of MMV Core v0.1-rc1.

## Future architecture (target shape)

Four cooperating layers; Secretary is the topmost:

| Layer | Role | Where it runs |
|---|---|---|
| **MMV Core** | routing / appraisal / governance / risk classification | local box, frozen at v0.1-rc1 |
| **Groq GPT-OSS 120B** | high-capacity external reasoning engine for heavy tasks | Groq cloud |
| **OpenCode** | resident agent frame (CLI / IDE-side runner) | local box |
| **Secretary** | cognitive-load reduction interface; uses MMV Core for routing/appraisal of its own outputs | runs on top of OpenCode + MMV Core |

In this stack:

- **MMV Core** is the trusted local arbiter — the routing engine
  decides whether Secretary's proposal is "answer-entitled" before any
  user-facing brief lands.
- **Groq GPT-OSS 120B** handles bulky reasoning Secretary needs (e.g.,
  scanning a 30k-line log, summarising a multi-day handover thread).
- **OpenCode** is the agent frame Secretary lives inside — it provides
  tool access (Bash, Read, Edit, etc.) and the conversation loop.
- **Secretary** is the policy on top of all of that: what to look at,
  what to surface, when to escalate.

## Permission stages

Secretary unlocks capability in stages. Each stage is gated by user
sign-off; nothing skips ahead.

| Stage | Capability | Hard limits |
|---|---|---|
| **Stage 0** | Read-only / report-only | No mutations anywhere; Secretary can only read files and emit a brief. |
| **Stage 1** | Proposal queue | Secretary writes proposals to a queue (file or DB); user processes the queue. |
| **Stage 2** | Doc-patch proposals | Secretary may produce patch files (`*.patch`) for docs only; user applies them manually. |
| **Stage 3** | Human-approved execution | User approves a queued proposal; Secretary executes the specific approved action only. |
| **Stage 4** | Limited autonomous maintenance | Whitelisted maintenance tasks (e.g., recompute a metadata file) run without per-action approval; the whitelist is small and explicit. |

Stage advancement requires a written user approval recorded in this
file (or a successor doc). Default Stage on first build: **Stage 0**.

## Hard boundaries (apply at every Stage)

These do not relax even at Stage 4:

- **No direct Core mutation.** Secretary does not edit files under
  `src/`, `prompts/`, `config/pattern_library/`, `data/pattern_library/`,
  or `data/raf/`.
- **No Pattern Library mutation.** Active patterns / quarantine /
  taxonomy / thresholds are immutable from Secretary's process.
- **No Golden set mutation.** `tests/golden_set/*.jsonl` is read-only
  to Secretary.
- **No autonomous commit.** Secretary may stage proposals but never
  invokes `git commit` without explicit user action.
- **No autonomous cron addition.** Secretary may not write to
  `crontab` or systemd timers.
- **No autonomous network egress to third parties** beyond what MMV
  Core normally uses (Brave / Groq / Ollama). Specifically: no posting
  to issue trackers, chat services, or webhooks without per-action
  approval.
- **No secret access.** Secretary reads only what it needs; `.env`,
  `~/.claude/`, and any `*credentials*` paths are off-limits.

These boundaries are enforced by:

1. The addon package layout (Secretary lives *outside* `src/`; e.g.,
   `addon/secretary/`).
2. A capability allow-list checked at startup.
3. Code review at each Stage promotion.

## Dogfooding rationale

Secretary is built on MMV Core to **stress-test the Core's API**:

- MMV's routing engine should classify Secretary's outbound briefs
  ("ask the user", "answer the user", "verify before answering") with
  the same governance the public Core promises external users.
- MMV's Pattern Library should recognise the canonical query shapes
  Secretary surfaces (status briefs are a meta-conversation pattern;
  this is exactly the "self-reference / meta-dialogue" sub-topic).
- ISM corpus drift caused by Secretary's reading should be observable
  through the standard Phase 4 metrics, not through a separate audit
  channel.

If MMV Core cannot host its own Secretary cleanly, that is signal that
the Core's API needs work — and the right place to fix it is in the
*next* Core release, not in Secretary's internals.

## Out of scope for Phase 5A

- Secretary code (this doc records strategy; code is a Phase 5B+ task).
- Choice of OpenCode vs alternative agent frames (decision deferred).
- Groq vs other reasoning-engine vendors (decision deferred).
- A test suite for Secretary (designed alongside Stage 0 implementation).

## Decision points the user can make next

1. **Approve the Stage 0 build** as a Phase 5B task (Read-only briefs).
2. **Approve the addon-package layout** (e.g., `addon/secretary/` in
   this repo vs a separate repo).
3. **Approve the four-layer architecture** (MMV / GPT-OSS / OpenCode /
   Secretary) as the target shape, or revise it.

None of those decisions are required to ship MMV Core v0.1-rc1.
