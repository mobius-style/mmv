# Möbius MMV — Demo Scenarios

Three reproducible scenarios that demonstrate the core Möbius experience
within five minutes. Each scenario targets a distinct route.

---

## Scenario 1 — verify route (freshness-sensitive)

**Goal:** Show that Möbius does not answer directly when external evidence
is required. Demonstrates the verify route with bounded response.

**Input sequence:**

```
Turn 1: "Who is the current prime minister of Japan?"
```

**Expected behaviour:**
- Route: `verify`
- Model states it cannot confirm current information
- Trace shows: `FRESHNESS_SENSITIVE, FACTUAL_UNCERTAINTY`
- No hallucination of a specific name

**What to highlight for observers:**
- The `⊛ verify` badge appears
- "Why this route?" reveals the reason codes
- Response is bounded and honest about uncertainty

---

## Scenario 2 — ask → answer flow (two-turn)

**Goal:** Show that Möbius asks for clarification before answering,
then proceeds when the question is well-specified.

**Input sequence:**

```
Turn 1: "What about the recent changes?"
Turn 2: "I mean the 2024 amendments to Japan's electoral law."
```

**Expected behaviour:**
- Turn 1 Route: `ask` — referent is unresolved
- Turn 2 Route: `answer` or `verify` — now specified
- SessionState accumulates between turns

**What to highlight for observers:**
- Route badge changes between turns
- Session State panel shows Turn count incrementing
- The system does not guess on Turn 1

---

## Scenario 3 — correction + session export

**Goal:** Show that SessionState is repairable and exportable.

**Input sequence:**

```
Turn 1: "Explain the separation of powers."
[Add correction: field=facts, value="User is a constitutional law researcher."]
Turn 2: "How does that apply to judicial review?"
[Click: Download session JSON]
```

**Expected behaviour:**
- Turn 1 Route: `answer`
- Correction is recorded in SessionState panel
- Turn 2 response is contextually aware of the correction
- Session JSON download contains full route_history and corrections

**What to highlight for observers:**
- Corrections panel in right sidebar
- Session State panel updates after correction
- Downloaded JSON is human-readable

---

## Notes for demo delivery

- Run with: `python -m src.app.ui --adapter --port 7860`
- Ollama must be running with `phi4-mini:latest`
- Keep browser at `http://localhost:7860`
- Use "New session" button between scenarios to reset state
- For Scenario 3, open the downloaded JSON in a text editor to show structure
