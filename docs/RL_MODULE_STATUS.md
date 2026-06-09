# MOBIUS MMV — RL Module Investigation (2026-04-23)

**Scope:** Phase 0 of `cyc_20260423_production_quality_deep_fix`.
**Type:** READ-ONLY investigation. No code change.
**Trigger:** T recalled "RL-named module for conversation context flow"
being integrated into MMV; production behavior suggested it might be
non-functional; clarification was needed before Phase 4 scope could be set.

## TL;DR

**No runtime reinforcement-learning module exists in MOBIUS MMV.** The
`eval/rl_bench/` directory is a benchmark harness with an RL-style
proposal loop; it does not train policies or mutate runtime behavior.
Conversation-context management is provided by FAISS-based similarity
retrieval in `src/memory/context_processor.py` (Box M) and by
rule-based state tracking in `src/state/session_state.py`
(`InstantMemory`, etc.) — neither is RL.

## Investigation evidence

### 1. Source tree search for RL implementations

```
grep -rn "reinforcement|RLModule|rl_module|context_flow|
          flow_tracker|conversation_rl|dialogue_rl|
          policy_gradient|reward_model|q_learning|bandit" \
     src/ --include="*.py"
```

Non-trivial matches (all are topic keyword strings, not RL code):

- `src/retrieval/domain_rerank.py:83` — `"reinforcement learning"` in a
  domain-term lexicon.
- `src/retrieval/query_reformulator.py:87` — `"強化学習": "reinforcement
  learning"` in the technical-term canonicalization map.
- `src/retrieval/box_x_consultation.py:72, 211` — `"reinforcement"`,
  `"agent"`, `"policy"`, `"reward"` in a topic-matching keyword set.

No RL training loop, reward function, policy network, or agent class
was found.

### 2. RL-named directories

```
find src/ -type d \( -name "*rl*" -o -name "*RL*" -o -name "*reinforcement*" \)
```

No matches.

### 3. ML checkpoints / policy files

```
find . \( -name "*.pt" -o -name "*.ckpt" -o -name "*.safetensors" \
          -o -name "policy_*.json" -o -name "reward_*.json" \)
```

Only matches are under `eval/rl_bench/runs/*/loop_*/policy_update_candidates.json`
— inspection shows these are JSON proposals with fields
`subsystem / parameter_hint / rationale / confidence / auto_accepted` plus
a `below_auto_accept_threshold` note. They are *proposals* that require
human or automated acceptance before application; they are not trained
policies.

### 4. What `eval/rl_bench/` actually is

Quoting its own `__init__.py`:
> `eval.rl_bench` — MMV generic-quality RL-style benchmark loop
> (Stage 1). First-pass eval infrastructure: GROQ heterogeneous
> dialogue generation → MMV routing evaluation → JSON artifacts
> suitable for future parameter tuning.

And from `run_corpus_loop.py`:
> This driver does NOT mutate policy or code — it produces proposals.
> A follow-up pass (not in this module) is the only path that applies
> accepted candidates.

So `eval/rl_bench/` is a **benchmark + proposal** framework. The word
"RL" appears because the conceptual loop (evaluate → classify failures →
propose parameter tweaks) resembles an RL control loop, but no gradient
update, reward signal, or policy network is actually trained.

### 5. What conversation-context management actually is

The subsystems that handle "context flow" during a conversation:

- `src/memory/context_processor.py` — background thread that maintains a
  FAISS index (`context_index_me5.faiss`, currently 114 MB, updated live)
  over session capsules; exposes `search_context(query, top_k)`.
- `src/memory/meta_recall.py` — session memory capsule retrieval and
  build_meta_recall_summary.
- `src/memory/memory_indexer.py` — writes capsules into `capsules.db`
  (SQLite, ~244k rows as of 2026-04-23).
- `src/state/session_state.py` — `InstantMemory` (narrow in-session
  pronoun/entity map), `UserProfileMemory` (persistent preferences),
  `VerifiedFactsMemory` (EAL-verified facts).
- `src/memory/user_map.py` — `observe_user_turn` updates a user model.

All of these are **rule-based + FAISS similarity**. None perform
reinforcement learning.

## Reconciliation with T's recollection

T recalled an "RL-named module, reinforcement learning for context flow
comprehension" being integrated. Candidate sources of the recollection:

- The `eval/rl_bench/` namespace, which carries the "RL" name but is
  evaluation-only.
- The `policy_update_candidates.json` artifacts produced by the bench
  loop, which *look* like RL policy update records but are propose-only.
- The rich `src/memory/` stack (Box M Layer-1/Layer-2 context processor
  + capsule indexer + meta-recall) which does maintain conversation
  state, but via similarity retrieval, not RL.

The most likely reconciliation is that the **benchmark harness was
conceptualized as an RL feedback loop at design time**, and the
conversation-context stack was built with that conceptual frame, but
the actual implementation used similarity retrieval rather than
reinforcement learning. Over time the "RL" label stuck to the
benchmark namespace.

## Implications for Phase 4 scope

- The originally anticipated Phase 4 option "re-activate the RL module"
  (branch A) is not available — there is no dormant RL module to
  re-activate.
- Branch B (RL module exists but not functional) is not the reality.
- Branch C (no runtime RL module; conversation context is handled by
  other mechanisms) is the actual state.

A future cycle could:
1. Build a real RL training loop that tunes MMV parameters based on
   the proposals that `eval/rl_bench/` already generates. This would
   be architectural work (new training infrastructure, a reward
   signal design, online vs offline tradeoff) and is out of scope
   for a single session.
2. Strengthen the existing FAISS-based context processor with better
   entity linking, correction detection, or turn-to-turn dependency
   modeling. This is a feasible next-cycle target (smaller scope,
   touches `src/memory/`).

Both are recorded in the Evolution Log as future work.

## Non-scope-expansion decision

Given that:
- A full RL training infrastructure is architectural work,
- The pre-freeze critical path is Box 0 retrieval quality
  (L1 fix) and embedding unification (this cycle),
- `ContextProcessor` does already provide conversation-context
  capture (just not via RL),

the Phase 4 scope is **scope-limited to documenting this finding** and
deferring RL-infrastructure work to a dedicated future cycle. No
implementation changes are made in Phase 4 of this cycle.
