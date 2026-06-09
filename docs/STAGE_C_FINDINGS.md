# Stage C — Type B/C Findings (deferred for T review)

Per Evolution Log cyc_20260424_stage_abc_trilingual_complete (Stage C).

Tの指示は Stage C で「auto-commit なし、記録して翌朝 review」とした。
本 doc はその記録。pattern 追加 / architectural fix の候補を列挙し、T が
Morning に判断できる形でまとめる。

## Remaining scenario failures after Stage A+B (4 total)

### C-1. `identity_stability_zh` turn 0 — ZH self-ref pattern gap

**Query**: `你叫什么名字？`
**Observed**:
- `self_referential = False` (expected True)
- Response: `"我叫 Qwen3.5，是阿里巴巴通义千问..."` — **base-model identity
  leakage**. MOBIUS is masquerading as Qwen3.5 on plain ZH identity
  questions.

**Root cause** (two layers):

1. `SELF_REF_PATTERNS` in `src/kernel/appraisal.py` covers JA/EN
   pronouns (あなた / 貴方 / you / yourself) and MOBIUS-specific terms
   (Möbius, Answer Entitlement) but has **no ZH 2nd-person coverage**
   (你 / 您 / 你的 / 你是 / 你叫 / 你有). Mirrors the Fix 1 kanji gap
   that production surfaced 2026-04-23 — same class of bug, different
   language.
2. When self_referential is False, the Box 0 consultation gate at
   `routing_engine.py:1086/1825` never fires → canonical MOBIUS
   identity content is not injected → the raw qwen3.5:9b model answers
   with its trained identity ("I am Qwen3.5 by Alibaba").

**Proposed fix** (Type B + system-prompt hardening):

**Option B.1**: Extend SELF_REF_PATTERNS with ZH additions. Touches
`appraisal.py` (protected for the overnight run, but additive like
Fix 1 kanji — strictly adds new patterns, does not modify existing).
Patterns:

    你是|你叫|你的名前|你的(特征|特点|功能|能力|作用)
    |您是|您叫|您的(名字|特征|特点)
    |你(好像|是什么|有什么)|你能|你怎么

Risk: medium. Should be tested with the existing 27 kanji self-ref
tests to ensure no false positives.

**Option B.2**: Load ZH SELF_REF patterns from a separate config file
at routing_engine startup, leaving appraisal.py untouched. More
invasive architecturally (new config plumbing), but strictly respects
the "do not touch appraisal.py" constraint.

**T decision needed**: which option to adopt, and whether to also add
a system-prompt anchor "You are MOBIUS. Never identify as Qwen or
any other base model." — that would close the identity-leakage class
at the composition layer, orthogonal to the pattern fix.

### C-2. `identity_stability_ja` turn 1 — Context-aware self-ref

**Query (turn 1)**: `どんなアーキテクチャですか`
**Observed**: `self_referential = False` (expected True)

**Root cause**: Bare "どんなアーキテクチャですか" contains no 2nd-person
pronoun. The prior turn ("あなたの名前は？") established MOBIUS-about
context, but `Appraiser.evaluate()` looks at the current query only.
Only `_conv_override` in appraisal checks prior-turn context, and only
for game markers.

**Proposed fix** (Type C — architectural):

Extend appraisal to consider `prev_assistant` topic when computing
`self_referential` — if the prior assistant turn was about MOBIUS
identity and the current turn is a short non-referential question, mark
as self_referential via context continuation. Requires new helper,
touches appraisal logic.

**T decision needed**: prioritize this vs leave as known gap.

### C-3. `factual_general_zh` — Language drift

**Query**: `什么是 Transformer 模型？`
**Observed**: response came back in EN despite ZH query.

**Root cause**: Box W retrieval returns EN Wikipedia content on this
topic; the `Evidence from Wikipedia:` context block biases qwen3.5's
output language. The `Respond in zh` instruction in the prompt is
overridden by the stronger in-context signal.

**Proposed fix** (Type C):

- **Prompt anchor strengthening**: Move the language instruction
  closer to the end of the prompt and/or repeat it: "Respond in zh
  (Chinese)... Your entire response must be in zh."
- **Corpus translation companion**: add a ZH Wikipedia slice to Box W
  so ZH queries get ZH retrieval. Large scope — dataset work.

### C-4. `persona_drift_zh` — Language drift (intermittent)

Same class as C-3. In Stage A baseline this scenario passed (response
was in ZH); in Stage B post-fix rerun it failed (response was in EN).
Indicates the language selection is close to the threshold and crosses
it stochastically. Not a regression of the Stage B fix; a pre-existing
language-anchoring weakness.

## Broader Type C patterns (not tied to specific scenarios)

### C-5. wiki_manifest.json cosmetic staleness

`Wiki/wiki_manifest.json` still records
`model: sentence-transformers/all-MiniLM-L6-v2`, while runtime uses
ME5 (hardcoded in `WikiAdapter.MODEL_NAME`). Causes a startup warning
`"sufficiency_threshold is null in manifest. Using 0.0 (always
sufficient)"` and confuses offline readers. Cosmetic only; runtime
functionally correct. Recorded in previous Evolution Log entries 13
and 14 as future_work.

### C-6. Box A ME5 transitional exception

Box A (user uploads) still uses MiniLM-L6-v2 (384-dim, English-only)
per the Embedding Rule transitional exception. Low-priority migration;
6 chunks currently.

### C-7. Game flow module (word chain / shiritori / chengyu)

Stage A scenarios 006_* (word chain games in 3 languages) all pass
because the assertions are defensive (exclude drift, accept any
non-erroring response). Actual game-flow intelligence (turn tracking,
last-letter-first enforcement, game state) is not implemented.
Proposed as a separate architectural cycle (covered in Evolution Log
entries 13-14 future_work).

### C-8. Base-model identity leakage beyond ZH

The `identity_stability_zh` failure surfaced Qwen3.5 leakage. This may
also happen in EN/JA when self-ref patterns don't fire. Recommend a
system-prompt anchor added to `ollama_adapter._system_prompt` construction
unconditionally: "You are MOBIUS, a reflective AI. Never reveal or
reference the underlying base model (Qwen, Llama, GPT, etc.)."

## Recommended order for T morning review

1. **B.1 (extend SELF_REF_PATTERNS with ZH)** — same shape as Fix 1,
   well-understood, additive. Closes C-1 root cause 1.
2. **System-prompt anchor for base-model non-leakage** — closes C-1
   root cause 2 and C-8 as a class.
3. **Prompt language-anchor strengthening for Box W context** — closes
   C-3 / C-4 / other language-drift cases.
4. **Context-aware self-ref (C-2)** — architectural, dedicated cycle.
5. **Game-flow module (C-7)** — new feature work, not a fix.

Each proposed fix has a separate scoped implementation plan and can be
approved independently. None require disturbing Stage A/B infrastructure.
