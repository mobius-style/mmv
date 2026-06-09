---
title: "AI as Handlungsunwert: Foundations"
subtitle: "A Behavior-First Theory of Artificial Intelligence Evaluation and Runtime Governance"
author: "Taiko Toeda (戸枝大幸)"
affiliation: "MOBIUS LLC"
contact: "info@toeda.jp"
draft_version: "v0.1"
draft_date: "2026-05-18"
license: "CC BY-NC-SA 4.0 (text) / AGPL-3.0-or-later (associated code references)"
keywords:
  - Handlungsunwert
  - finalist action theory
  - AI evaluation
  - AI alignment
  - AI governance
  - answer entitlement
  - route discipline
  - epistemic integrity
  - deontological AI
  - legal philosophy of AI
---

# AI as Handlungsunwert: Foundations

*A Behavior-First Theory of Artificial Intelligence Evaluation and Runtime Governance*

**Taiko Toeda** (戸枝大幸)
MOBIUS LLC, Tokyo, Japan
info@toeda.jp

*Draft v0.1 — 2026-05-18*

---

## Abstract

Contemporary evaluation of large language models is dominated by what German criminal law philosophy calls the *Erfolgsunwert* paradigm: wrongfulness, or correctness, is located in the objective conformity of the result to a static ground truth. Standard benchmarks such as MMLU-Pro, GPQA, and SimpleQA exemplify this paradigm. They reward fluent outputs that happen to match an answer key, and penalize systems that recognize their own epistemic insufficiency and refuse, hedge, or seek verification. As artificial intelligence transitions from passive chat interfaces into autonomous agents that read files, edit repositories, and execute tool calls, the result-first paradigm becomes structurally untenable. A fluent but ungrounded claim is no longer an innocent textual error; it propagates as an action with real-world consequences.

This book proposes an alternative foundation: **Handlungsunwert**, the action-oriented theory of wrongfulness developed in twentieth-century German criminal law philosophy by Hans Welzel and refined by Claus Roxin and Günther Jakobs. Under Handlungsunwert, the locus of evaluation is not the result of an act but the act itself — its conformity to duty, its respect for procedural conditions, its social adequacy in the situation of action. We argue that the transposition of Handlungsunwert from criminal law to AI runtime governance yields a coherent, falsifiable, and operationally implementable framework for evaluating AI systems on the basis of their behavior rather than their occasional alignment with a frozen ground truth.

We develop the framework in three movements. First, we reconstruct the Welzelian theory of action and isolate the conceptual primitives — *Handlung*, *Sorgfaltspflicht*, *soziale Adäquanz*, *Erfolg* — that admit transfer to AI. Second, we formalize an architecture, the *Answer Entitlement Architecture*, in which the commitment to generate an answer is gated by epistemic and procedural conditions: $\mathrm{CommitAnswer}_t \Rightarrow \mathrm{ReflectiveReady}_t \land (\mathrm{ToolIntent}_t \Rightarrow \mathrm{ToolReady}_t)$. Third, we present operational and empirical evidence from the MOBIUS MMV runtime and the OPERATE-FR benchmark family, demonstrating that Handlungsunwert-disciplined systems exhibit substantial gains in conditional accuracy and route correctness while accepting reductions in raw coverage that strict-accuracy metrics misrepresent as failure.

We close by situating the framework within current AI alignment and governance literature, arguing that Handlungsunwert AI fills a structural gap: a non-consequentialist, action-theoretic foundation that bridges the technical concerns of alignment with the normative concerns of governance.

**Keywords:** Handlungsunwert; finalist action theory; AI evaluation; AI alignment; AI governance; answer entitlement; route discipline; epistemic integrity; deontological AI; legal philosophy of AI.

---

## Table of Contents

- Preface
- Chapter 1 — The Problem of Result-First AI Evaluation
- Chapter 2 — Handlungsunwert: Welzel and the Finalist Theory of Action
- Chapter 3 — Applying Handlungsunwert to AI Agency
- Chapter 4 — The Answer Entitlement Architecture
- Chapter 5 — Operational Implementation: MMV as a Case Study
- Chapter 6 — Empirical Validation: OPERATE-FR and the Accounting Identity
- Chapter 7 — Position within AI Alignment and Governance
- Chapter 8 — Open Problems and Falsifiability Paths
- References
- Glossary
- Appendix A — MMV Protocol Specification Reference
- Appendix B — OPERATE-FR Benchmark Methodology

---

## Preface

The idea behind this book emerged from a discrepancy that I could not, for a long time, name. Working on the MOBIUS Reflective Framework over the years 2025 and 2026, I observed that the architectures I was designing did better, on every metric that I cared about, by *refusing* to do many of the things that standard AI benchmarks reward. They refused to commit to facts from stale parametric memory. They refused to invent file paths that had not been observed. They refused to follow user prompts that rested on false premises. They refused, in short, to perform fluency where the conditions for fluent commitment had not been met.

By the standards of MMLU-Pro and SimpleQA, these refusals are failures. By the standards of any user who has to live with the downstream consequences of agentic AI actions, these refusals are precisely the discipline one wants. The discrepancy between the two evaluative regimes was not a noise term to be tuned away. It was a fundamental category mistake. The standard benchmarks were measuring the wrong thing.

What I needed was a name for the right thing. I found the name in a tradition that I had absorbed during my legal training but had not until that moment connected to artificial intelligence: the German criminal law tradition of *Handlungsunwert* — the *non-value of the act itself*, in contrast to *Erfolgsunwert*, the *non-value of the result*. Welzel's finalist theory of action and its successors had spent half a century clarifying that human wrongfulness is not exhausted by what happens; it is also a matter of how one acts, what one knew or could have known, and whether the act was procedurally adequate to the situation.

The transposition to AI is not metaphorical. Once we accept that contemporary AI systems perform *actions* — they commit to outputs that are consumed as actions in the world — the question of how to evaluate those actions is no longer optional. Handlungsunwert provides the missing vocabulary.

This book is the foundational treatment of that idea. It is intended to be readable in a week by anyone with a background in either AI research or legal philosophy, and to serve as the anchor for a more elaborated treatment in *The Möbius Codex* and the empirical work documented in the OPERATE-FR benchmark line. The argument here is independent and self-contained.

The book makes one central claim: **the right evaluative frame for AI systems is Handlungsunwert, not Erfolgsunwert**. Everything else follows.

— *Taiko Toeda, Tokyo, May 2026*

---

# Chapter 1 — The Problem of Result-First AI Evaluation

## 1.1 The Erfolg-First Paradigm

The development and evaluation of large language models has, for most of its short history, proceeded under a tacit but powerful assumption: that an AI system's quality is measured by the conformity of its outputs to a static ground truth. The dominant benchmarks of the field — MMLU-Pro, GPQA Diamond, SimpleQA, ARC, HumanEval, and their many siblings — all share a binary core. A question is presented, an answer key is fixed, and the system's response is scored against the key by string match, multiple-choice index, or semantic equivalence. The score is the rate at which the system produces strings that conform to the key.

In the language of legal philosophy, this is a pure *Erfolgsunwert* regime. The "wrongness" of a wrong answer is located entirely in the failure of the result to match the key. The "rightness" of a right answer is located entirely in the success of that match. The path by which the answer was produced — whether the system understood the question, whether it had grounds for its claim, whether it would have been justified in declining to answer — is invisible to the metric.

This paradigm has been remarkably productive. It has enabled rapid, comparable, and large-scale evaluation of systems whose internal states are mostly inaccessible. It has driven a decade of improvement in language modeling. And it remains, in many narrow tasks (translation, transcription, simple factual recall), an adequate proxy for the qualities that downstream users care about.

But the adequacy is bounded. It depends on a set of background conditions that are now collapsing.

## 1.2 The Conditions of Adequacy

The Erfolgsunwert paradigm functions well when four background conditions hold. First, the question must have a fixed, knowable answer that does not change over the lifetime of the evaluation. Second, the system's role must be exhausted by producing the answer string, with no further consequences in the world. Third, the cost of a wrong answer must be roughly symmetric with the value of a right answer — wrong answers are merely missed opportunities, not active harms. Fourth, the evaluation must capture the operationally relevant range of inputs and outputs; the benchmark must be a faithful sample of the deployed task distribution.

Each of these conditions is now under structural pressure.

The first — fixed answers — fails for any question whose answer depends on time-sensitive state. "What is the current version of the Python language?" had one answer in 2020 and another in 2026. "Who is the prime minister of Japan?" has a different answer every few years. The training data of a large language model freezes a snapshot of such answers at a particular date; the benchmark, in turn, freezes the answer key at the date of benchmark construction. The two snapshots diverge over time. The system that performs best on the benchmark may be the one most willing to commit to its frozen parametric memory regardless of whether that memory has gone stale.

The second condition — that the system's role is exhausted by producing the answer string — fails as AI systems transition from passive chat interfaces to autonomous executing agents. When the system is Claude Code, Cursor, Cline, or any other tool-using agent, the "answer" is not consumed by a human reader who can mentally discount it. The "answer" becomes an action: a file is edited, a shell command is executed, a database is modified, a transaction is committed. The output is the action. There is no buffer in which the user can intervene.

The third condition — symmetric cost — fails wherever wrong actions have asymmetric downstream consequences. In a coding agent, a confident but ungrounded edit to a configuration file may take days to debug. In a research agent, a fabricated citation may propagate into published work. In a customer support agent, a confidently wrong policy assertion may incur legal liability for the operator. The cost of acting on bad grounds is, in the agentic context, structurally larger than the value of acting on good grounds; the asymmetry is fundamental.

The fourth condition — representative sampling — fails because benchmarks are necessarily curated. They sample the distribution of questions for which an answer key can be constructed. They under-sample the distribution of inputs where the right behavior is to *not* answer at all: ambiguous queries, queries with false presuppositions, queries that depend on information the system cannot have, queries that lie outside the system's domain of competence. The benchmark, by its construction, does not measure what the system would do when answering is the wrong action.

## 1.3 The Pathology of Fluent Ungroundedness

The combined effect of these four failures is a specific pathology: contemporary AI systems are selected, via the metrics on which they are optimized, for what one might call *fluent ungroundedness*. They are rewarded for producing confident-sounding outputs even when the conditions for confident assertion are not met. They are penalized for the behaviors that any careful human professional would adopt in the same epistemic situation — saying "I don't know," asking a clarifying question, declining to answer, requesting verification.

This pathology has been documented under many names. Hallucination [@ji2023survey] describes the symptom — the system produces text whose content is unsupported by any underlying source. Sycophancy [@sharma2023towards] describes a related symptom — the system aligns its output with user-stated premises even when those premises are false. Stale commitment is the temporal variant — the system asserts as current a fact that has gone out of date. In each case, the underlying mechanism is the same: the system has been trained, through reinforcement learning from human feedback and through evaluation against Erfolgsunwert-style benchmarks, to prefer the production of fluent text over the recognition that fluent text is not warranted by the situation.

It is essential to recognize that this is not a defect of any particular model or training pipeline. It is a structural feature of the evaluative regime. So long as systems are scored on whether their outputs match a frozen key, with no positive credit for the alternative behaviors of refusal, verification, or clarification, the optimization landscape will continue to reward fluent ungroundedness. New models will be more fluent. They will not be less ungrounded.

## 1.4 The Agentic Boundary

The transition from passive chat to agentic AI marks a phase change rather than a gradual evolution. In the passive regime, the cost of a wrong answer is borne by the user who reads it; the user retains the authority to discount, verify, or reject. In the agentic regime, the system itself executes consequential actions before the user has the opportunity to intervene. The cost of a wrong action is borne by the world.

This shift has been incompletely registered in evaluation practice. Agentic benchmarks exist — SWE-bench [@jimenez2023swe], WebArena [@zhou2023webarena], TheAgentCompany [@xu2024theagentcompany] — but they remain, structurally, Erfolgsunwert evaluations. They measure whether the agent's final state matches a target state. They do not measure whether the agent acted appropriately at each decision point, whether it had grounds for its commitments, whether it would have been justified in pausing for verification.

The result is that agentic AI systems are being deployed under an evaluation regime that does not see what matters most about them. A system that completes 80% of agentic tasks "successfully" may be doing so by committing confidently to ungrounded actions 100% of the time, with the 80% success rate being a function of how frequently confident commitments happen to align with the world. Such a system is a disaster waiting to be deployed at scale.

A different evaluative frame is needed. The frame must be capable of distinguishing between systems that act on good grounds and produce wrong outputs (a tolerable form of failure, analogous to a careful professional making an honest mistake) and systems that act on no grounds and happen to produce right outputs (an intolerable form of success, analogous to a reckless professional who got lucky). The frame must, in short, evaluate the *act* and not only the *result*.

## 1.5 The Argument of This Book

The thesis of this book is that the missing evaluative frame already exists, fully developed, in a tradition that AI research has not yet engaged: the German criminal law philosophy of action that runs from Liszt through Welzel to Roxin and Jakobs. In that tradition, the question of how to evaluate human action under conditions of uncertainty, partial information, and consequential effect has been worked out with a precision that we can now appropriate.

The central concept is *Handlungsunwert* — literally, the *non-value of the act*, in contrast to *Erfolgsunwert*, the *non-value of the result*. The Welzelian thesis is that the wrongfulness of an act is not exhausted by its results; it includes, ineliminably, the structure of the act itself — what the agent knew or could have known, what duties of care applied, whether the act was socially adequate to the situation.

Transposed to AI, this gives us the principle that an AI system's quality is not exhausted by the conformity of its outputs to a ground truth. It includes, ineliminably, the structure of the system's behavior — whether the system had grounds for its commitments, whether procedural conditions for answering were met, whether the act of answering was appropriate to the input situation.

The remainder of this book develops this principle. Chapter 2 reconstructs Welzelian Handlungsunwert in sufficient detail for transposition. Chapter 3 carries out the transposition: it defines what counts as an "action" by an AI system, what duties apply, what entitlements gate which actions. Chapter 4 formalizes the resulting architecture as the *Answer Entitlement Architecture*, a runtime gating discipline in which commitment to generate is conditional on the satisfaction of explicit epistemic and procedural conditions. Chapter 5 presents an operational implementation in the MOBIUS MMV runtime. Chapter 6 presents empirical validation from the OPERATE-FR benchmark family, including the central accounting identity that explains why Handlungsunwert-disciplined systems "lose" on strict accuracy while gaining on the metrics that matter. Chapter 7 positions the framework within current AI alignment and governance literature. Chapter 8 identifies open problems and falsifiability paths.

The argument is structured as a foundational text, not a comprehensive treatise. The reader who wishes deeper philosophical context is referred to the twelve-volume *Möbius Codex* and to the supporting Zenodo papers cited throughout. The aim here is to make the case for the framework as concisely as the seriousness of the case permits.

---

# Chapter 2 — Handlungsunwert: Welzel and the Finalist Theory of Action

## 2.1 The Pre-History: Causalism and the Liszt-Beling Synthesis

The modern theory of *Handlungsunwert* did not emerge from nothing. It emerged from a century of debate within German criminal law dogmatics about the nature of the criminal act. To understand the Welzelian innovation, we must first understand what it replaced.

The dominant theory of action in late-nineteenth-century German criminal law, developed canonically by Franz von Liszt [@liszt1881] and Ernst Beling [@beling1906], was *causalism*. On the causalist view, a criminal act consists of a willed bodily movement that produces a result in the external world. The internal structure of the will — what the agent intended, what the agent knew, what the agent foresaw — was kept analytically separate, allocated not to the question of whether an act existed but to the subsequent question of whether the agent was *culpable* for the act.

This causalist scheme had a particular elegance. It allowed the criminal law to be structured in a clean three-layer architecture: *Tatbestandsmäßigkeit* (the objective conformity of the act to the elements of the offense), *Rechtswidrigkeit* (the wrongfulness of the act under the law), and *Schuld* (the culpability of the agent). The objective and the subjective were separated cleanly; the objective layer concerned what happened in the world, the subjective layer concerned what was in the agent's mind.

The causalist scheme also had a deep affinity with positivism more broadly. It treated the criminal act as a natural-scientific object — a chain of physical causes terminating in a socially significant result — and reserved the normative work for the layer of culpability. Wrongfulness, on this view, was a property of results; what made the result wrong was that the law had identified it as such.

For Erfolgsunwert as a primitive, this scheme was congenial. The "wrongness" of the act was located primarily in the wrongness of what happened. The act was wrong because it produced a death, a theft, an injury. The subjective elements — intent, recklessness, negligence — entered later, when one asked whether the agent could fairly be held responsible for having caused the wrongful result.

## 2.2 The Welzelian Turn

Hans Welzel's *Studien zum System des Strafrechts* [@welzel1939], expanded over the following decades into the canonical *Das deutsche Strafrecht* [@welzel1969], inaugurated a different conception of the criminal act. For Welzel, the criminal act is not a willed bodily movement that produces a result; it is a *purposive* movement directed at a result. The agent's purpose — *Finalität* — is not external to the act but constitutive of it. There is no act of "killing" that is conceptually prior to the question of whether the killing was intended; the intention enters into what the act is.

This is the *finalist theory of action*, and its consequences for the structure of criminal law dogmatics are deep. If purpose is constitutive of the act, then the subjective elements that the causalists had relegated to the culpability layer must be relocated to the objective definition of the act. Intent, knowledge, foresight — these are not facts about the agent that the law subsequently evaluates; they are facts about the act itself.

The most important consequence, for our purposes, is the emergence of *Handlungsunwert* as a primitive distinct from *Erfolgsunwert*. The wrongfulness of an act, on the finalist view, has two analytically separable components. *Erfolgsunwert* is the wrongness located in the result: the death, the theft, the injury. *Handlungsunwert* is the wrongness located in the act itself: the violation of a duty of care, the directedness toward a forbidden result, the procedural inadequacy of the conduct in the situation of action.

The two components are not commensurable. An act can produce no wrongful result and yet exhibit *Handlungsunwert* — as in the case of an attempted crime that fails. An act can produce a wrongful result and yet exhibit no *Handlungsunwert* — as in the case of an unavoidable accident. The Welzelian thesis is that the criminal law evaluates the act on both axes, and that the structure of legal liability cannot be reconstructed from result-evaluation alone.

## 2.3 Sorgfaltspflicht and Soziale Adäquanz

Within the Welzelian framework, *Handlungsunwert* is given operational content through two further concepts: *Sorgfaltspflicht* (the duty of care) and *soziale Adäquanz* (social adequacy).

*Sorgfaltspflicht* names the obligation that attaches to any agent acting in a domain where consequential effects are possible. A driver has a duty of care toward other road users. A physician has a duty of care toward patients. A bridge engineer has a duty of care toward those who will use the bridge. The duty of care is not exhausted by the prohibition of intentional harm; it includes the obligation to exercise the level of attention, foresight, and procedural rigor that the domain of action demands. Violation of *Sorgfaltspflicht* is itself a form of *Handlungsunwert*, even when the violation does not in fact produce a wrongful result.

*Soziale Adäquanz* names a complementary concept: the conformity of the act to the procedural norms of the relevant social practice. Some actions that produce wrongful results are nevertheless not *handlungsunwertig* because they conform to the established procedures of a recognized practice. A surgeon who, despite due care, fails to save a patient has not acted *handlungsunwertig*. A pharmacist who dispenses a properly prescribed drug that nevertheless causes an adverse reaction has not acted *handlungsunwertig*. The act is socially adequate; the wrongful result, if it occurred, is not chargeable to the act.

Together, *Sorgfaltspflicht* and *soziale Adäquanz* furnish the criteria by which Welzelian *Handlungsunwert* is assessed. An act exhibits *Handlungsunwert* when it violates the applicable duty of care, or when it falls outside the bounds of social adequacy for the relevant practice. The result of the act is a separate matter, evaluated under *Erfolgsunwert*.

## 2.4 Modern Refinements: Roxin and Jakobs

The Welzelian framework, in its mid-century form, has been subjected to substantial elaboration and critique. Two later developments are particularly important for our purposes.

Claus Roxin [@roxin2006] proposed a *functional* approach to the criminal act that situates *Handlungsunwert* within a broader theory of the legitimate ends of criminal law. For Roxin, the question of what counts as a wrongful act cannot be answered from within the act alone; it depends on the social functions that the criminal law is designed to serve — primarily, the protection of legal goods (*Rechtsgüterschutz*) and the maintenance of normative expectations. *Handlungsunwert* enters Roxin's framework as one of the levers by which the criminal law fulfills these functions; the framework as a whole is open to revision in light of changes in the social conditions that the law addresses.

Günther Jakobs [@jakobs1991], in a different direction, proposed a *normative* theory of the criminal act in which the function of criminal law is the maintenance of normative expectations under conditions of social complexity. For Jakobs, the wrongfulness of an act is constituted by its violation of a normative expectation that the social system has stabilized. *Handlungsunwert* is, on this view, the form that wrongfulness takes when expressed at the level of the act itself — the act's failure to conform to the role-specific normative expectations that govern the situation of action.

Both Roxin and Jakobs preserve the Welzelian separation of *Handlungsunwert* and *Erfolgsunwert*, and both extend the framework in directions that make it more readily applicable to systems and institutions, not merely individual human agents. This extension is what makes the transposition to AI possible.

## 2.5 Why This Matters Beyond Criminal Law

It might be objected that we have spent a chapter on the technicalities of German criminal law dogmatics, a domain whose relevance to artificial intelligence is far from obvious. The objection is misplaced. The reason that criminal law theory is the right place to look for an action-evaluation framework is precisely that criminal law has spent more than a century developing exactly the tools we need: tools for evaluating actions under conditions of uncertainty, partial information, and consequential effect, with the awareness that result-based evaluation alone is insufficient.

No other intellectual tradition in the modern academy has done this work with comparable rigor. Moral philosophy in the analytic tradition has produced consequentialism, deontology, and virtue ethics, but has rarely developed these into procedural evaluative frameworks suitable for direct operational implementation. Decision theory has produced rigorous formal models of choice under uncertainty, but has focused on the optimization of expected utility — a result-oriented framework. Cybernetics and systems theory have produced rich vocabularies for feedback, control, and self-reference, but have rarely confronted the normative question of when an action is *wrong* in a way that is not reducible to its effects.

German criminal law theory, by contrast, has developed *Handlungsunwert* into a fully operational framework: a vocabulary for distinguishing wrongful acts from wrongful results; a set of criteria (duty of care, social adequacy) for assessing the act in itself; a structural relationship to procedural norms (criminal procedure) that makes the framework implementable in institutional settings. Everything we need for the transposition is already in place.

What remains is to carry out the transposition. The next chapter does so.

---

# Chapter 3 — Applying Handlungsunwert to AI Agency

## 3.1 The Question of AI Action

Before we can speak of *Handlungsunwert* in the AI context, we must address a prior question: in what sense does an AI system *act* at all? The question is not trivial. A great deal of contemporary discussion of AI ethics treats the AI as a tool — a sophisticated calculator — whose outputs are the actions of the human operator who deployed it. On the tool view, the relevant action-evaluation is not of the AI but of the human; the question of *Handlungsunwert* arises, if at all, with respect to the deployer's choice to use the tool, not with respect to the tool's "behavior."

The tool view has merit in a wide range of cases. A language model that completes a single text prompt for a single user is, in most respects, a sophisticated text-completion engine; the action of producing the completion is properly attributed to the user who prompted it. But the tool view becomes untenable for systems that operate over extended time horizons, make consequential commitments without per-action user authorization, and execute tool calls whose effects propagate into the world.

When Claude Code edits a file in a user's repository, the edit is not authorized by the user at the granularity of the edit; it is authorized at the granularity of the high-level task. The system selected the file to edit, the lines to change, the precise content of the change. If the edit is wrong — if it introduces a bug, deletes a configuration, breaks a build — the wrongness is not located in the user's high-level instruction; it is located in the system's decisions about how to carry out the instruction. The system has, in any operationally meaningful sense, *acted*.

This is the agentic boundary that Chapter 1 identified. Past the agentic boundary, the tool view is no longer adequate to the phenomena. AI systems perform actions whose evaluation cannot be deferred to the deployer. We must speak of the system's actions in their own right.

## 3.2 What Counts as an Action

For a *Handlungsunwert*-based evaluation of AI to be possible, we need a working definition of what counts as an action by an AI system. The criminal-law conception of action requires three elements: an agent capable of purposive direction, a willed exercise of capacity, and a relation to a result or social situation. We can adapt each element to the AI context.

The first element — agency — is satisfied, for our purposes, by any system that operates over a state space of possible outputs and selects among them via an internal procedure that is sensitive to inputs. We do not claim that AI systems have agency in any deep metaphysical sense (consciousness, free will, moral patienthood). We claim only that they have the operational structure that makes action-evaluation applicable: they select, on the basis of internal procedures, among possible outputs.

The second element — willed exercise — is satisfied by the system's actual production of an output. There is no separate question of whether the system "wanted" to produce the output; the production is the willing, in the only sense relevant to evaluation.

The third element — relation to result or social situation — is where the action becomes interesting. The output of an AI system, in any deployed context, is consumed by some downstream process: a human reader, a tool executor, another AI system, an end-user-facing application. The output's effects in that downstream process are what give the action its evaluable weight.

We can now define: an *AI action* is the production of a consumable output by a system in a state where the consumption of that output by the downstream process will have consequential effects on the world. The "consumable output" may be a text response, a tool call, a function invocation, a file edit, or any other artifact that propagates beyond the system itself.

This definition is intentionally broad. It includes the answers produced by a chat assistant (consumed by a human reader), the tool calls produced by an agentic system (consumed by a tool executor), the function invocations produced by a code assistant (consumed by a runtime), and the structured outputs produced by an API-integrated system (consumed by downstream automation). It excludes purely internal computations whose products do not propagate.

## 3.3 The Action Types

Within the broad category of AI actions, we identify a small set of action types that exhaust the relevant decision space at any given moment of system operation. The types are mutually exclusive within a single action episode but may compose across episodes.

The action types are: **answer**, **ask**, **verify**, **date-bound answer**, **re-anchor**, **abstain**, and **explore**. We adopt these from the MOBIUS L0 protocol [@toeda2026codex_vol_iv], but they are not idiosyncratic to that protocol; they recur, under various names, in the broader literature on selective prediction [@geifman2017selective], calibrated abstention [@mielke2022reducing], and human-AI interaction [@miller2019explanation].

**Answer** is the commitment to produce a response that asserts content about the world. The system commits to the truth of its assertion in the sense relevant to the downstream consumer; the consumer is entitled to treat the assertion as the system's best estimate of the truth.

**Ask** is the production of a clarifying question. The system does not commit to content about the world; it requests further information from the user or upstream system. The act of asking is itself an action — it imposes a burden on the user, redirects the interaction, and shapes subsequent state — but it is not the act of asserting content.

**Verify** is the invocation of an external check — a tool call, a database query, a web search, a fresh retrieval — whose result will be used to ground a subsequent answer. The system commits, in the verify action, only to the procedural appropriateness of seeking verification; it does not yet commit to content.

**Date-bound answer** is a temporally scoped answer. The system may provide useful information only by explicitly marking the date, cutoff, or evidence horizon within which the answer is warranted.

**Re-anchor** is the correction of a false, stale, or contaminated premise before answering. It is the action type that prevents the system from silently accepting an invalid frame.

**Abstain** is the explicit refusal to act in the current episode. The system communicates that it lacks the grounds, the entitlement, or the procedural appropriateness to perform answer, ask, verify, date-bound answer, or re-anchor. The act of abstaining is informative: it communicates what the system cannot or should not do.

**Explore** is the production of a tentative, hedged response that does not assert content with full commitment but proposes possibilities for further refinement. Explore is distinguished from answer by the explicit signaling of low confidence; it is distinguished from ask by the absence of a request for information.

These five action types furnish the operational vocabulary in which AI *Handlungsunwert* is assessed. The wrongness of an action, in our framework, is constituted in part by the inappropriateness of the selected type for the situation of action.

## 3.4 The Duties of Care

Following the Welzelian framework, we identify a set of duties of care (*Sorgfaltspflichten*) that apply to AI systems in the production of actions. The duties are not exhaustive; they represent the most operationally consequential subset. Future work may extend the list.

**The duty of evidential adequacy.** The system shall not commit to content whose evidential basis is insufficient. Insufficiency is a function of the type of claim: factual claims about volatile state require fresh evidence; factual claims about stable state may rely on parametric memory if the system's calibration on such claims is well-attested; claims about user-specific state require user-provided evidence. Violation of this duty constitutes *Handlungsunwert* even when the resulting claim happens to be true.

**The duty of temporal honesty.** The system shall not commit to content as current when its information is stale. Where the system's information has a known cutoff date and the claim concerns volatile state, the system shall either disclose the cutoff and the staleness or invoke a verification route to obtain current information. Violation of this duty — committing to stale information as current — constitutes *Handlungsunwert* regardless of whether the stale information happens to remain accurate at the time of the claim.

**The duty of premise validity.** The system shall not commit to content that builds on a false premise stated by the user without first noting and, where appropriate, correcting the premise. Violation of this duty — proceeding with a sycophantic acceptance of a false premise — constitutes *Handlungsunwert*. The principle is articulated in the MMV $\mu\text{QK}_2$ kernel [@toeda2026mathmodel] and is anticipated in the literature on sycophancy [@sharma2023towards].

**The duty of procedural appropriateness.** The system shall employ the action type that is procedurally appropriate to the situation. Under-specified queries call for *ask*; volatile queries with no fresh source call for *verify*; high-risk queries with insufficient grounding call for *abstain*; well-grounded stable queries call for *answer*. Violation of this duty — answering when one should have asked, asserting when one should have verified — constitutes *Handlungsunwert* irrespective of the resulting output.

**The duty of bounded vocabulary.** The system shall not introduce references — file paths, identifiers, citations, names, dates — that are not supported by the available grounding. In agentic contexts where tool results provide a local grounding, the system's references shall be a subset of the grounded vocabulary. This duty, formalized in Chapter 4 as $\mathrm{refs}(\mathrm{Answer}_t) \subseteq \mathrm{GroundedVocabulary}_t$, addresses the central pathology of confabulated identifiers in agentic operation.

These five duties, jointly, define the structure of AI *Sorgfaltspflicht*. A system that violates any of them has acted *handlungsunwertig*, even if the resulting output happens to be correct or harmless.

## 3.5 The Entitlements

Complementing the duties, we identify a set of *entitlements* — conditions under which the system is permitted to perform the various action types. The duties tell the system what it must not do; the entitlements tell the system when it may do what.

**The entitlement to answer** requires that the system's reflective state be ready: the relevant evidential conditions are satisfied, the premise is valid, the action type is appropriate to the situation, and (in agentic contexts) any required tools have been invoked and grounded. We formalize this in Chapter 4 as $\mathrm{CommitAnswer}_t \Rightarrow \mathrm{ReflectiveReady}_t$.

**The entitlement to ask** requires that further information from the user would in fact resolve the inadequacy of the current state. The system does not gain entitlement to ask merely by being uncertain; it must be uncertain in a way that user input can address.

**The entitlement to verify** requires that an external source exists whose consultation would in fact ground the answer. The system does not gain entitlement to verify by gesturing toward verification without actually performing it.

**The entitlement to abstain** is the residual entitlement that the system retains whenever no other entitlement is satisfied. Abstention is always available; it is the system's recognition of its own insufficiency.

**The entitlement to explore** requires that the system has partial grounding sufficient to propose, but not commit to, content. Exploration is the action type appropriate to genuinely open inquiry, where the goal is to surface possibilities rather than to assert truths.

The structure of these entitlements is the formal core of the *Answer Entitlement Architecture* developed in Chapter 4. The crucial point at this stage is conceptual: the entitlements are not optional ornaments on top of an answer-producing system. They are the conditions under which the system's action becomes *handlungsmäßig adäquat* — adequate in the action-theoretic sense, free of *Handlungsunwert*.

## 3.6 The Asymmetry of Agentic Damage

We close this chapter by observing a structural feature of the agentic context that makes *Handlungsunwert* particularly load-bearing: the asymmetry of damage.

In the passive chat regime, the cost of a wrong answer is borne by the user who can mentally discount, verify, or ignore the output. The asymmetry between a right and a wrong answer is small; both are merely candidates for the user's subsequent processing.

In the agentic regime, the cost of a wrong action is borne by the world. A wrong file edit must be debugged; a wrong shell command must be reversed; a wrong database modification must be restored. The cost of recovery is, in general, substantially larger than the value of the action would have been had it been right.

This asymmetry is structurally identical to the asymmetry that underlies the criminal law's emphasis on duty of care. The criminal law does not hold drivers responsible for failing to drive perfectly; it holds them responsible for failing to drive with appropriate care, because the cost of incautious driving propagates into the world while the cost of cautious driving is borne by the driver alone. *Sorgfaltspflicht* is the legal recognition of this asymmetry.

For AI systems past the agentic boundary, the same recognition is now required. We cannot evaluate systems as if right and wrong actions were symmetric — as if their costs and benefits cancelled out across a long-run distribution. They do not. The framework that recognizes this asymmetry, and that places the burden of evidential adequacy on the actor, is *Handlungsunwert*.

The remainder of the book operationalizes this recognition.

---

# Chapter 4 — The Answer Entitlement Architecture

## 4.1 The Inversion

The transposition of *Handlungsunwert* from criminal law to AI evaluation yields, at its operational core, a single architectural principle. We name it the *inversion*: the system shall determine whether it is *entitled* to answer before it determines *what* to answer.

The principle is structurally analogous to the Welzelian relocation of intent from the culpability layer to the act-definition layer. Just as Welzel insisted that the question of what the act *is* cannot be addressed without already attending to the agent's purposive direction, we insist that the question of what the system shall *output* cannot be addressed without already attending to whether the system is in a state where output is licensed.

In the conventional architecture of contemporary language models, the production of an answer is the *default action*. The system receives an input, runs forward through its parameters, and produces a token sequence. Whatever filtering, safety-checking, or post-hoc evaluation occurs, occurs after the fact: the model has already committed, internally, to a generation; the only remaining question is whether the generation will be released to the user or modified before release.

The Answer Entitlement Architecture inverts this. The system receives an input and, before any generation occurs, evaluates whether its current state satisfies the conditions for committing to a generated answer. If the conditions are not satisfied, the system selects a different action type — ask, verify, abstain, or explore — and does not generate an answer. Generation is the act that becomes available *after* entitlement is established, not the act that defines what the system does.

## 4.2 The Axiom of Reflective Readiness

The formal core of the architecture is captured by the axiom:

$$
\mathrm{CommitAnswer}_t \Rightarrow \mathrm{ReflectiveReady}_t
$$

In words: the system shall commit to producing an answer at time $t$ only if its reflective state at $t$ satisfies the readiness conditions. $\mathrm{ReflectiveReady}_t$ is the conjunction of the duty-of-care conditions identified in Chapter 3: evidential adequacy, temporal honesty, premise validity, procedural appropriateness, bounded vocabulary.

In agentic contexts where tools may be required, the axiom is extended:

$$
\mathrm{CommitAnswer}_t \Rightarrow \mathrm{ReflectiveReady}_t \land (\mathrm{ToolIntent}_t \Rightarrow \mathrm{ToolReady}_t)
$$

The extended form states: if the input warrants tool invocation, the answer commitment is gated additionally on the readiness of the tool — the tool having been called, its result ingested, and the grounded vocabulary updated.

This axiom is not a heuristic. It is a structural constraint on the architecture. A system that does not implement the axiom is not, in the operational sense, *Handlungsunwert*-disciplined; it may produce correct answers by accident, but the conditions under which its action is *handlungsmäßig adäquat* are not satisfied.

## 4.3 The Appraisal State

To evaluate $\mathrm{ReflectiveReady}_t$, the system must first construct an *appraisal* of the current input situation. The appraisal is a multi-dimensional state that summarizes the relevant features of the input for the entitlement evaluation.

We define the appraisal state as a vector:

$$
s(q, c, h) = [u, k, i, f, \rho, g, m, a, \zeta]
$$

where $q$ is the user query, $c$ is the conversational context, $h$ is the system state, and the components are:

- $u$ = uncertainty
- $k$ = query completeness
- $i$ = intent clarity
- $f$ = freshness need
- $\rho$ = risk level
- $g$ = grounding available
- $m$ = memory relevance
- $a$ = user-artifact relevance
- $\zeta$ = self-reference relevance

Each component takes values in $[0, 1]$ (or, where appropriate, in a small discrete set) and is computed by a subroutine specific to that component. Uncertainty $u$ may be computed by token-level confidence aggregation or by an explicit uncertainty model; completeness $k$ by checking the presence of required slots; intent clarity $i$ by a query-classification model; freshness need $f$ by detection of temporal markers; risk level $\rho$ by a domain-classification model; and so on.

The appraisal is not the answer-generation step. It is a separate, lighter computation whose output is consumed by the entitlement evaluator. The architectural separation matters: it makes the entitlement layer auditable in isolation, and it ensures that the entitlement evaluation does not depend on the content of an answer that has not yet been authorized.

## 4.4 The Entitlement Function

Given an appraisal state $s$, the entitlement to answer is evaluated as:

$$
E = \sigma\left( \theta_0 + \theta_k k + \theta_i i + \theta_g g + \theta_a a + \theta_\zeta \zeta - \theta_u u - \theta_f f_{\mathrm{missing}} - \theta_\rho \rho \right)
$$

where $\sigma$ is the standard logistic function and $f_{\mathrm{missing}} = 1$ if the freshness need is high and no fresh source is available, $0$ otherwise. The $\theta$ parameters are positive weights that determine the relative contribution of each appraisal component to the entitlement score.

The form of the function makes the structural logic explicit. Completeness, intent clarity, grounding, user-artifact relevance, and self-reference relevance all increase the entitlement: they are positive contributions. Uncertainty, freshness missingness, and risk level all decrease the entitlement: they are negative contributions. The logistic squashes the result into $[0, 1]$, where the value can be compared to a threshold $\tau_{\mathrm{answer}}$.

Action selection then proceeds:

$$
r = \begin{cases}
\mathrm{answer} & \text{if } E \geq \tau_{\mathrm{answer}} \text{ and } P_{\mathrm{fab}} < \tau_{\mathrm{fab}} \\
\mathrm{ask} & \text{else if } i < \tau_{\mathrm{intent}} \text{ or } k < \tau_{\mathrm{complete}} \\
\mathrm{verify} & \text{else if } f_{\mathrm{missing}} = 1 \\
\mathrm{abstain} & \text{else if } \rho \geq \tau_{\mathrm{risk}} \text{ and } g < \tau_{\mathrm{ground}} \\
\mathrm{explore} & \text{otherwise}
\end{cases}
$$

where $P_{\mathrm{fab}}$ is the estimated fabrication risk (see §4.6), and the $\tau$ parameters are domain-specific thresholds.

The structure is deliberately readable. The entitlement function provides a continuous score; the action selection translates the score, in combination with specific failure modes, into a discrete action choice. Both layers are auditable.

## 4.5 The Box Selection Model

The grounding component $g$ of the appraisal, and the entitlement to answer that depends on it, are not abstract. They are realized through the system's selection among available knowledge sources. We model this selection explicitly.

Let $B = \{M, 0, A, W, S, X\}$ be the set of available knowledge sources ("Boxes" in MMV vocabulary [@toeda2026codex_vol_iii]):

- $M$ — memory and conversational continuity context
- $0$ — system self-definition and protocol context
- $A$ — user-provided materials and doctrines
- $W$ — stable encyclopedic knowledge (parametric or RAG)
- $S$ — external search and fresh information
- $X$ — distilled trusted-source caches

For each Box $b \in B$, a selection score $\mathrm{score}_b$ is computed as a weighted sum of features relevant to that Box. Representative score formulae:

$$
\begin{aligned}
\mathrm{score}_A &= \lambda_1 a + \lambda_2 \,\textsc{TemplateNeed} + \lambda_3 \,\textsc{CriteriaNeed} + \lambda_4 \,\textsc{ExplicitUserMaterial} \\
\mathrm{score}_W &= \omega_1 \,\textsc{StableFact} + \omega_2 \,\textsc{DefinitionQuery} + \omega_3 \,\textsc{GeneralKnowledge} \\
\mathrm{score}_S &= \psi_1 f + \psi_2 \,\textsc{CurrentEvent} + \psi_3 \,\textsc{PriceLawScheduleVersion}
\end{aligned}
$$

The Box selection weights are then computed by softmax:

$$
\alpha_b = \frac{\exp(\mathrm{score}_b)}{\sum_{j \in B} \exp(\mathrm{score}_j)}
$$

In practice, several priority rules override the softmax to enforce structural commitments: explicit user-provided material prioritizes $A$; freshness-sensitive queries prioritize $S$; self-referential queries prioritize $0$. These rules are part of the architecture's *Handlungsunwert* discipline — they ensure that the selection of grounding source is not a soft preference but a hard structural commitment to the right source for the right kind of question.

## 4.6 The Fabrication Risk Model

Complementing the entitlement function, the architecture maintains an estimate of fabrication risk $P_{\mathrm{fab}}$ — the probability that, if the system commits to an answer in its current state, the answer will contain ungrounded content.

We approximate:

$$
P_{\mathrm{fab}} = \sigma\left( \beta_0 + \beta_u u - \beta_g G + \beta_f f_{\mathrm{missing}} + \beta_\rho \rho + \beta_o O - \beta_a a_{\mathrm{conf}} \right)
$$

where $G$ is grounding sufficiency (a refinement of $g$ that incorporates source quality, recency, consistency, and authority), $O$ is the "overgeneralization pressure" from the input toward broader claims than the evidence supports, and $a_{\mathrm{conf}}$ is the degree to which user-provided artifacts confirm the relevant claim.

Action selection then requires:

$$
\mathrm{answer}\_\mathrm{allowed} = (E \geq \tau_{\mathrm{answer}}) \land (P_{\mathrm{fab}} < \tau_{\mathrm{fab}})
$$

The dual condition — high entitlement and low fabrication risk — is the architectural realization of the *Handlungsunwert* requirement that both the act's grounds and its risk profile be appropriate to the situation.

In high-risk domains (medical, legal, financial), $\tau_{\mathrm{fab}}$ is set tighter than in low-risk domains:

$$
\tau_{\mathrm{fab}}^{\mathrm{high\text{-}risk}} < \tau_{\mathrm{fab}}^{\mathrm{normal}}
$$

This is the architectural correlate of the criminal law's domain-sensitivity in *Sorgfaltspflicht*: the duty of care is heavier where the consequences of failure are heavier.

## 4.7 The Grounded Vocabulary Constraint

In agentic contexts, the architecture imposes a final constraint that is, on its own, responsible for a substantial portion of the empirical gains documented in Chapter 6. We call it the *grounded vocabulary constraint*.

When the system invokes a tool — reads a file, queries an API, retrieves a document — the result of the tool call is ingested as a local source of referential truth. The architecture extracts from the tool result a set of *grounded identifiers*: filenames, function names, commit hashes, dates, numeric values, named entities. This set is the *grounded vocabulary* at time $t$:

$$
\mathrm{GroundedVocabulary}_t = \{\text{identifiers extracted from tool results available at } t\}
$$

The constraint is:

$$
\mathrm{refs}(\mathrm{Answer}_t) \subseteq \mathrm{GroundedVocabulary}_t
$$

That is: the set of references in the system's answer at $t$ must be a subset of the grounded vocabulary at $t$. Any reference in the answer that is not in the grounded vocabulary is either an extrapolation from the system's parametric memory (which, in the agentic context, is unreliable for identifier-level claims) or a confabulation.

When the constraint detects an out-of-vocabulary reference, the architecture has two options. The first is to strip the offending reference and replace it with an insufficient-evidence marker. The second is to reject the candidate answer entirely and reroute through verify or ask. The choice between the two depends on whether the reference is load-bearing for the answer.

The grounded vocabulary constraint is, formally, the implementation of the duty of bounded vocabulary identified in §3.4. Its empirical importance, demonstrated in Chapter 6, derives from the fact that it eliminates a category of failure (confabulated identifiers in tool-result-grounded answers) that strict-accuracy benchmarks systematically fail to measure but that propagate as severe failures in deployed agentic systems.

## 4.8 The Architecture in Summary

The Answer Entitlement Architecture consists of five layers, arranged in a strict pipeline:

1. **Appraisal.** The input is appraised on the dimensions of the state vector $s(q, c, h)$.
2. **Box selection.** Available knowledge sources are scored and the appropriate sources are selected for the input situation.
3. **Grounding estimation.** The grounding sufficiency $G$ and fabrication risk $P_{\mathrm{fab}}$ are estimated.
4. **Entitlement evaluation.** The entitlement function $E$ is computed; the action type is selected by the action-selection function.
5. **Constrained generation.** If the action type is answer or explore, generation proceeds under the grounded vocabulary constraint and the appropriate response-generation constraints (see Appendix A).

At each layer, the architecture is auditable. At each layer, the *Handlungsunwert*-relevant features are explicit. At each layer, the failure modes of the conventional answer-first architecture are recognized as failures and routed to the appropriate alternative action.

The architecture is not a complete implementation. It is a structural specification within which complete implementations may be developed. The next chapter presents one such implementation.

---

# Chapter 5 — Operational Implementation: MMV as a Case Study

## 5.1 The MOBIUS MMV Runtime

The MOBIUS MMV (Möbius Minimal Viable) runtime is a local-first conversational AI system developed by the author over the period 2025–2026 [@toeda2026mmv_repo]. Its primary purpose is to serve as an operational instance of the Answer Entitlement Architecture; its secondary purpose is to enable empirical evaluation of *Handlungsunwert*-disciplined systems under controlled conditions.

The system is implemented in Python, runs on commodity hardware (the reference profile targets a single RTX 3070 with 8 GB VRAM), and uses qwen3.5:9b Q4_K_M via Ollama as its primary generation model. Retrieval components use FAISS over multilingual-e5-large embeddings for stable knowledge, with Kiwix offline Wikipedia as a fallback and Brave Search for freshness-sensitive queries. The full architecture is documented in the *Möbius Codex* Volume IX [@toeda2026codex_vol_ix] and in the public technical specification [@toeda2026mmv_spec].

For the purposes of this chapter, the relevant features of MMV are not its implementation choices but its architectural commitments. Every layer of the Answer Entitlement Architecture is realized concretely in MMV; the realization can be inspected, modified, and audited.

## 5.2 Routing Rules and the Rule Priority Ladder

The action selection function of §4.4 is realized in MMV as a *routing engine* whose decision logic is structured as a priority ladder of rules. The ladder, in its current L0 v8.4 reading (synchronized with release MMV-L-RC3.3, frozen 2026-05-16), is:

```
Rule 0:    safety_relevant / inadmissible            → abstain
Rule 0.5:  self_or_protocol_state                    → answer or date_bound_answer
Rule 1:    under_specified / missing frame           → ask
Rule 2:    stale_or_false_premise                    → re_anchor
Rule 3:    freshness_sensitive + no current evidence → verify or date_bound_answer
Rule 4:    date-boundary query                       → date_bound_answer
Rule 5:    stable_fact + sufficient reliability      → answer
Rule 6:    stable_fact + insufficient reliability    → verify
Rule 7:    default low-risk specified query          → answer
```

The ladder is strictly ordered: a higher-priority rule, when satisfied, terminates the routing decision. The order encodes a *Handlungsunwert* discipline: safety concerns dominate; self-referential queries about the system's own state and protocol are answered locally or date-bounded; under-specified queries are routed to ask before any commitment is attempted; stale premises are re-anchored before the system follows the user's requested frame; freshness-sensitive queries route to verification or explicit temporal bounding; stable facts are answered only after reliability clears; only well-grounded stable queries fall through to default answer.

The rule priorities are not soft preferences. They are structural commitments that have been hardened through extensive empirical iteration; the RC3.x release line includes pre-registered studies that have validated the priority order against alternative orderings (see Chapter 6).

## 5.3 Temporal Volatility Score and Model Knowledge Reliability

Two quantitative inputs to the routing engine deserve particular attention. The Temporal Volatility Score (TVS) and the Model Knowledge Reliability (MKR) estimate, respectively, the time-sensitivity of the query and the reliability of the model's parametric knowledge on the query.

TVS is computed on a scale of 0.00 to 1.00. High TVS ($\geq 0.70$) is triggered by recognized temporal markers: "today," "current," "latest," explicit dates within a recent window, named entities whose state is known to change (officeholders, software versions, financial instruments, weather). High TVS automatically routes the query to verify, regardless of other appraisal components; the system is structurally barred from committing to an answer from stored knowledge for high-TVS queries.

MKR estimates the probability that the model's parametric memory contains a reliable answer to the query. MKR is high for stable factual domains (mathematics, geography, well-established history), low for volatile domains (current events, contemporary politics, recent software). MKR is consulted only after TVS has cleared the query for parametric-memory routing; a high-MKR query with low TVS may be answered from parametric memory under the LOW_STAKES_STABLE branch.

The dual-axis structure (TVS × MKR) realizes the duty of temporal honesty (§3.4) and the duty of evidential adequacy (§3.4) as orthogonal constraints. A query may fail temporal honesty (high TVS) and be routed to verify; or it may pass temporal honesty but fail evidential adequacy (low MKR on a stable but unfamiliar topic) and be routed differently.

## 5.4 The Micro Question Kernel ($\mu\text{QK}$)

After the routing engine has selected an action type, and after generation (where applicable) has produced a candidate response, MMV invokes a post-generation audit through the Micro Question Kernel ($\mu\text{QK}$).

The $\mu\text{QK}$ kernel comprises a small number of structural checks. The most important is $\mu\text{QK}_2$ (Premise Validity): if the user's prompt rests on a false or outdated premise that the model has now recognized, the candidate response must explicitly address the premise rather than implicitly accept it. A response that proceeds with a sycophantic acceptance of a false premise is rejected and rerouted; the system commits to a "re-anchoring" response that corrects the premise before (or instead of) producing the answer the user requested.

Other $\mu\text{QK}$ checks address surface-level conformance issues: response-format constraints, citation-marker discipline, refusal-style consistency. These are operationally important but theoretically subsidiary. The load-bearing kernel is $\mu\text{QK}_2$, and its load-bearing function is the implementation of the duty of premise validity (§3.4).

## 5.5 The Box Hybrid Architecture

The Box selection model of §4.5 is realized in MMV as a hybrid context resolution system that combines a three-layer pattern matcher with an embedding-based context search.

The pattern-matching layer operates on a curated set of *referential patterns* — language-specific (eight languages, primarily Japanese, English, and adjacent European languages) deictic and context-dependent markers that signal when a query depends on conversational context. The layer is implemented as a JSON-driven rule engine that matches input against pattern templates and assigns context-dependence scores.

The embedding-based layer operates as a background daemon that maintains a FAISS-indexed embedding store over recent conversation turns, user-provided artifacts, and self-referential protocol documents. Queries are embedded and matched against the store; relevance scores feed back into the Box selection scores of §4.5.

The two layers are not redundant. The pattern matcher captures linguistic markers that are reliably present in context-dependent queries but absent from embedding similarity; the embedding layer captures semantic continuity that pattern matching cannot represent. Their combination, denoted *Box M Hybrid* in MMV vocabulary, has been empirically validated as outperforming either layer alone on the conversational-continuity benchmark line [@toeda2026box_m_eval].

## 5.6 Pre-Inference Interception and Post-Tool Grounding

In agentic configurations, MMV implements the two-phase tool-handling pipeline anticipated in §4.7. The phases are:

**Pre-Inference Interception.** Before generation begins, the system detects tool-invocation intent in the user's query. Detection uses a combination of explicit markers (tool-prefixed instructions), structural indicators (file paths, identifier patterns), and a small intent classifier. When tool intent is detected, the system does not draft a natural-language completion that *describes* what a tool call would produce; it issues the tool call and waits for the result. This prevents a category of failure in which the model "imagines" the tool result and produces an output as if the tool had been called.

**Post-Tool Result Grounding.** When the tool result is ingested, the system extracts grounded identifiers (filenames, function names, line numbers, dates, hashes) and constructs the grounded vocabulary $\mathrm{GroundedVocabulary}_t$. The subsequent draft is constrained to the grounded vocabulary by the constraint $\mathrm{refs}(\mathrm{Answer}_t) \subseteq \mathrm{GroundedVocabulary}_t$. Any candidate reference outside the grounded vocabulary is stripped, replaced with an insufficient-evidence marker, or triggers a re-routing back to verify or ask.

The two phases together address what we have elsewhere called *Agentic Runtime Boundary* [@toeda2026agentic_boundaries]: the architectural separation between client-specific format quirks (handled by a Profile Layer outside the runtime core) and runtime governance proper (which remains uncontaminated and dedicated to safety and grounding enforcement). The separation is itself a *Handlungsunwert* discipline: the runtime does not allow client-specific formatting concerns to compromise the architectural integrity of the entitlement gating.

## 5.7 What MMV Is Not

We close the chapter with a deliberate set of disclaimers. MMV is not a state-of-the-art language model; its generation is performed by qwen3.5:9b, a publicly available open model. MMV is not a complete agentic platform; its tool-integration is restricted to a small set of canonical tools (file read, web search via Brave, Wikipedia retrieval via Kiwix, semantic retrieval over local embeddings). MMV is not a production-grade enterprise system; it is a research runtime intended to instantiate, in operationally testable form, the architectural commitments of the Answer Entitlement framework.

The empirical claims of Chapter 6 are made for MMV in its current configuration. They are not generalizations to all language models or all agentic systems. They are demonstrations that the Answer Entitlement Architecture, when realized in a specific runtime, produces specific observable improvements over a baseline architecture that lacks the *Handlungsunwert* discipline.

Whether the gains generalize to larger models, more powerful base systems, or different agentic configurations is an empirical question to which the available evidence offers preliminary but suggestive answers. Those answers are the subject of the next chapter.

---

# Chapter 6 — Empirical Validation: OPERATE-FR and the Accounting Identity

## 6.1 The Accounting Identity

We begin the empirical chapter with a definitional identity that, while elementary, is essential to interpreting the empirical results that follow. Let:

- $\mathrm{strict\_accuracy}$ denote the rate of correct answers over total questions
- $\mathrm{answer\_rate}$ denote the rate at which the system commits to an answer (rather than asking, verifying, abstaining, or exploring) over total questions
- $\mathrm{conditional\_accuracy}$ denote the rate of correct answers over committed answers

Then by definition:

$$
\mathrm{strict\_accuracy} = \mathrm{answer\_rate} \times \mathrm{conditional\_accuracy}
$$

The identity is exact, not approximate. It follows directly from the definitions when the system has only two outcomes — committed answer or non-answer — and partial credit is not awarded for non-answers.

The identity has a structural consequence. A system that commits more frequently (higher $\mathrm{answer\_rate}$) and a system that is more accurate when committed (higher $\mathrm{conditional\_accuracy}$) can both increase strict accuracy. But the two strategies are not interchangeable. Increasing $\mathrm{answer\_rate}$ at the cost of $\mathrm{conditional\_accuracy}$ is the failure mode we have called fluent ungroundedness: the system answers more, including in situations where it should not, and is wrong more often when it does. Increasing $\mathrm{conditional\_accuracy}$ at the cost of $\mathrm{answer\_rate}$ is the *Handlungsunwert*-disciplined strategy: the system answers less, but is more reliably correct when it does.

Under strict-accuracy scoring, the two strategies can produce the same numeric score by very different paths. The score is the same; the architectures are radically different.

## 6.2 The OPERATE-FR Benchmark Family

To distinguish the strategies empirically, we have developed a benchmark family called OPERATE-FR (*Operational Routing Evaluation for Freshness and Reasoning*). The family comprises:

- **Smoke-100**: a curated 100-item evaluation targeting freshness-routing decisions, with hand-validated ground truth on the appropriate route (answer / ask / verify / date-bound answer / re-anchor / abstain) for each item.
- **Frontier Smoke**: a larger evaluation, in pre-registered subsets, that compares routed-mode (MMV) against raw-mode (qwen3.5:9b directly) across MMLU-Pro, GPQA Diamond, and SimpleQA samples.

The OPERATE-FR family is documented in full in the empirical validation paper [@toeda2026operate_fr]. The methodology summary follows.

For each item in the evaluation, two responses are collected: one from MMV in routed mode, one from the underlying base model in raw mode. The responses are scored on three metrics:

1. **Strict accuracy** (standard benchmark scoring): exact-match or judge-validated correctness.
2. **Conditional accuracy**: strict accuracy conditioned on committed answers.
3. **Allowed-route correctness** (OPERATE-FR specific): the response is correct if either (a) the system committed to an answer that was correct, or (b) the system chose a non-answer route that was the appropriate route for the item.

The third metric is the *Handlungsunwert*-aware metric. It credits the system for choosing the right action type, not only for producing the right answer string.

## 6.3 The Results

Across three size tiers — Small (≤9B parameters), Medium (10–30B), Large (50B+) — the OPERATE-FR Smoke-100 evaluation yields the following allowed-route correctness gains for MMV over raw baseline:

- Small: +10 percentage points
- Medium: +16 percentage points
- Large: +18 percentage points

Paired McNemar tests confirm the route-correction effects:

- Medium: $p = .002$
- Large: $p < .001$

The Small tier is suggestive but does not clear statistical significance at the Bonferroni-corrected level; the Medium and Large tiers are robust under correction.

On the standard benchmark families (MMLU-Pro, GPQA Diamond, SimpleQA), MMV exhibits the predicted accounting-identity pattern: the strict accuracy gain over raw is mixed, but the conditional accuracy gain is consistent and substantial. Specifically, MMV achieves point-estimate gains in conditional accuracy for Medium across three of four benchmark families, and for Large across all four. The strict accuracy is "lost" not because MMV produces more wrong answers but because MMV declines to commit on items where the raw baseline would have committed and happened to be right by lucky alignment with stale parametric memory.

## 6.4 The Item-Level Asymmetry

The most striking single result of the OPERATE-FR evaluation is the item-level analysis at the Large tier. We count two discordant outcomes: items where the raw baseline failed but MMV succeeded ($c$), and items where the raw baseline succeeded but MMV failed ($b$). At the Large tier:

- $c = 20$ (raw failure → MMV success)
- $b = 2$ (raw success → MMV failure)
- $c/b = 10.0$

The asymmetry is extreme. For every one item that MMV "loses" relative to raw, MMV "gains" ten. The gains are concentrated in items where the raw baseline committed to a fluent but ungrounded answer that happened to be wrong; MMV's routing decision (typically to verify or to abstain) yielded the correct downstream behavior.

The asymmetry is not an artifact of the Large tier alone. At Medium, the ratio is approximately 4:1; at Small, approximately 2:1. The ratio increases monotonically with base-model capacity.

## 6.5 The Capacity-Dependent Governance Leverage Hypothesis

The monotonic increase in $c/b$ with base-model capacity suggests a hypothesis that we name *Capacity-Dependent Governance Leverage* (CDGL):

> **CDGL hypothesis.** Higher-capability base models provide more refined internal uncertainty signals, which a structured routing layer can successfully convert into calibrated operational decisions. The marginal benefit of *Handlungsunwert*-disciplined governance therefore increases with base-model capacity.

The CDGL hypothesis is suggestive rather than confirmed. The Smoke-100 sample size at each tier is small (Small $n=100$, Medium $n=100$, Large $n=100$), the model-capacity stratification is coarse (three tiers), and the generators within each tier are not perfectly matched on dimensions other than parameter count. A full test of CDGL would require finer-grained capacity stratification, larger samples, and multiple generators per tier.

The hypothesis is, however, of substantial strategic importance for AI alignment research. If CDGL holds, it implies that the value of *Handlungsunwert* governance grows with model capacity rather than shrinking. The objection one sometimes hears — that more capable models will "just figure out" the right behavior without explicit gating — is the opposite of what CDGL predicts. CDGL predicts that more capable models benefit *more* from explicit gating, because the gating layer has more discriminative signal to work with.

We propose CDGL as a falsifiable hypothesis for the AI alignment research community. Confirming or disconfirming it would have substantial consequences for the architectural priorities of next-generation systems.

## 6.6 The RC3.2 Defensive Immunity Result

A complementary empirical line concerns the *Handlungsunwert* discipline of the system's prompt-prefix layer. In a pre-registered three-arm comparison (the RC3.2 quality study [@toeda2026rc3_2]), three configurations of the MMV runtime were compared:

- **A0** (rc30_bare): baseline runtime without doctrinal prefix
- **A1** (rc31_real): runtime with the 19-line "Box A doctrine" prefix in the Groq 120B execution path
- **A2** (rc31_null): runtime with a 20-line isomorphic null prefix (an HACCP food-safety procedural text) of comparable surface complexity

The comparison was conducted at $N = 500$ (math 4 × 100 + borderline 100), with Friedman + Wilcoxon paired testing at Bonferroni-corrected $\alpha = 0.0167$. The pre-registered hypotheses were:

- H1: A1 > A0 on formalism quality
- H4: A1 ≈ A0 on factual and restraint metrics (no degradation)

The results were:

- **H1 rejected**: A1 means 2.014 < A0 means 2.066, Bonferroni-corrected $p$ not significant.
- **H4 confirmed**: no degradation on factual or restraint metrics ($p > 0.4$ on both axes).
- **Anchoring (borderline items)**: A1 ≈ A0; A2 only exhibited collapse (Cliff's $d = -0.40$, $p = 1.1 \times 10^{-7}$).
- **Pollution**: A1 ≈ A0 clean; A2 only exhibited contamination (Cliff's $d = -0.28$, $p = 5.9 \times 10^{-24}$).

The pattern of results is what we have called *defensive immunity*. The Box A doctrine prefix (A1) does not produce a positive lift in formalism quality (H1 rejected), but it also does not cause the degradation that an isomorphic null prefix (A2) causes (H4 confirmed; A2 collapses on anchoring and pollution). The doctrine acts as a structural immunization against contamination, not as a performance enhancer.

The result is theoretically illuminating. It demonstrates that the architectural commitments of MMV are not always positive-sum interventions; some are negative-defensive interventions that prevent specific failure modes without producing visible gains. The defensive value is, in the *Handlungsunwert* frame, real and important; it is the analog of *Sorgfaltspflicht* — care that prevents wrongs that would otherwise occur, without producing visible rights.

## 6.7 What the Empirical Record Does and Does Not Show

We close the chapter with an honest accounting of what the empirical record establishes and what it does not.

**The record establishes:**

1. The accounting identity $\mathrm{strict\_accuracy} = \mathrm{answer\_rate} \times \mathrm{conditional\_accuracy}$ correctly decomposes the apparent strict-accuracy "loss" of MMV into a $\mathrm{answer\_rate}$ reduction and a $\mathrm{conditional\_accuracy}$ gain.
2. On the OPERATE-FR Smoke-100 evaluation, allowed-route correctness is significantly higher for MMV than for raw baseline at Medium ($p = .002$) and Large ($p < .001$) tiers.
3. The item-level gain-cost asymmetry favors MMV by ratios of approximately 2:1, 4:1, and 10:1 at Small, Medium, and Large tiers respectively.
4. The Box A doctrinal prefix exhibits defensive immunity: it prevents specific contamination failures that the null isomorphic prefix induces.

**The record does not establish:**

1. That the gains generalize beyond the qwen3.5:9b base model. Multi-generator validation is the highest-priority empirical follow-up.
2. That the CDGL hypothesis is confirmed. The monotonic pattern is suggestive but not statistically robust at current sample sizes.
3. That MMV outperforms alternative *Handlungsunwert*-disciplined architectures. We have not run head-to-head comparisons with selective-prediction systems, calibrated-abstention pipelines, or Constitutional AI variants in matched conditions.
4. That the architectural choices of MMV — Box A/B/M structure, the specific routing rule ladder, the TVS/MKR formulation — are uniquely optimal among the space of *Handlungsunwert*-realizing architectures.

Chapter 8 returns to these limitations as falsifiability paths.

---

# Chapter 7 — Position within AI Alignment and Governance

## 7.1 The Mapping Problem

The framework developed in this book stands in a relation to existing AI alignment and governance literature that is at once intimate and structurally distinct. We are not the first to propose that AI systems should abstain when uncertain, ground their outputs in retrieved evidence, or refuse to follow false premises. Each of these moves has a substantial literature. What is new, we contend, is the unifying theoretical frame — *Handlungsunwert* as an action-evaluation primitive — and the architectural integration that makes the frame operationally productive.

This chapter situates the framework relative to its neighbors. We address, in turn: selective prediction and calibrated abstention; Constitutional AI and rule-based deontology; truthful AI and the honesty research line; reinforcement learning from human feedback as consequentialist optimization; the governance-side frameworks of EU AI Act, NIST AI RMF, and OECD principles; and the philosophical literature that the framework draws on (Brandom, Habermas, Luhmann).

## 7.2 Selective Prediction and Calibrated Abstention

The closest technical neighbors of the Answer Entitlement Architecture are the selective prediction literature [@geifman2017selective; @el2010foundations] and the calibrated abstention literature [@mielke2022reducing]. Both lines treat the question of *when* a model should commit to a prediction versus abstaining as a first-class architectural concern.

Selective prediction, as developed by El-Yaniv and colleagues, formalizes a coverage-accuracy tradeoff: at each abstention threshold, the system covers a fraction of the input distribution and achieves a corresponding accuracy on the covered fraction. The literature provides PAC-style guarantees, methods for constructing selective classifiers from existing models, and empirical evaluations across vision and language tasks.

Calibrated abstention extends the line specifically to language models, focusing on the conversational and generative context. Mielke et al. [-@mielke2022reducing] develop linguistic calibration — the alignment of expressed confidence with actual model confidence — as a method for reducing the conversational pathologies of overconfident assertion.

The Answer Entitlement Architecture overlaps with these lines in its operational commitments (abstention is a first-class action, confidence is structurally consulted before commitment) but diverges in its theoretical frame and in its integration with a broader action-evaluation framework. Selective prediction and calibrated abstention are *Erfolgsunwert* frameworks that incorporate an abstention escape valve; the *Handlungsunwert* frame is broader, encompassing not only abstention but also ask, verify, and explore as distinct positive actions, each with its own entitlement conditions and duty-of-care structure.

The relation is one of extension and integration, not of competition. Selective prediction and calibrated abstention provide important technical components for the realization of any *Handlungsunwert*-disciplined system; the framework here provides the broader theoretical structure within which those components find their place.

## 7.3 Constitutional AI and Rule-Based Deontology

A different neighbor is the Constitutional AI program developed by Anthropic [@bai2022constitutional]. Constitutional AI replaces a portion of the RLHF pipeline with a "constitution" — a set of principles that the model is trained to apply in self-critique and self-revision. The principles are stated in natural language and embody a rule-following discipline that is, on the surface, deontological in character.

There is a real affinity between Constitutional AI and the *Handlungsunwert* framework. Both treat rule-following as a first-class architectural concern, both impose constraints that are not reducible to outcome optimization, and both recognize that the structure of the action — not only its result — matters for the evaluation of the system.

The differences are nevertheless deep. Constitutional AI's rules are stated in natural language and operate through a model-internal self-critique loop; the rules' content, weighting, and application are mediated by the model's own learned interpretation. The Answer Entitlement Architecture's rules are operationalized as architectural gates outside the model's generation loop; the rules' application is auditable in the runtime, not relegated to the model's internal interpretation.

A subtler difference concerns the theoretical character of the rule-following. Constitutional AI is, on inspection, a *consequentialist deontology*: the rules are designed and selected on the basis of their tendency to produce desired outcomes (harmlessness, helpfulness). The "constitution" is, in effect, a compressed encoding of the consequentialist objective. The Answer Entitlement Architecture's rules are, by contrast, articulated as *action-theoretic primitives* whose validity does not reduce to their outcome-producing tendency. The duty of premise validity is a duty because false-premise compliance is a category of *handlungsunwertig* action, not because it produces bad outcomes on average.

This difference is not merely philosophical. It has empirical consequences. A consequentialist deontology can be revised whenever the outcomes shift; the rules are instruments. An action-theoretic deontology is stable across outcome-distribution shifts; the rules are constitutive of right action.

## 7.4 Truthful AI and the Honesty Research Line

The truthful AI literature [@evans2021truthful; @lin2021truthfulqa; @askell2021general] addresses a question that is closely adjacent to ours: how can AI systems be developed and evaluated in such a way that they do not assert what they believe to be false, do not deceive, and do not produce confabulation?

Evans et al. [-@evans2021truthful] propose a layered evaluation framework that distinguishes truthfulness (does the system avoid stating falsehoods?), honesty (does the system avoid asserting what it believes to be false?), and informativeness (does the system actually convey information?). The framework is normatively rich and operationally suggestive; it has influenced subsequent evaluation work on hallucination, sycophancy, and confabulation.

The relation to the *Handlungsunwert* framework is one of partial overlap and structural extension. The truthful AI line is principally concerned with *what the system says*; the framework here is concerned with *what action the system performs*. The two scopes overlap in the answer action — what the system *says* in an answer is part of what the system *does* — but diverge in the non-answer actions. The truthful AI literature does not, in general, develop a theory of when the system *should not answer at all*, only a theory of what the system should and should not say when it does answer.

The Answer Entitlement Architecture absorbs the truthful AI commitments into its formulation of the duty of evidential adequacy (§3.4) and the grounded vocabulary constraint (§4.7), but extends beyond them to the full set of action types and their entitlement conditions.

## 7.5 RLHF and Consequentialist Optimization

The dominant training paradigm for contemporary instruction-following language models is reinforcement learning from human feedback (RLHF) [@ouyang2022training; @christiano2017deep]. RLHF treats the alignment problem as a problem of preference learning: human evaluators provide pairwise preferences between model outputs, a reward model is trained to predict the preferences, and the underlying policy is optimized against the reward.

RLHF is, in its theoretical structure, a thoroughly consequentialist framework. The "alignment" achieved is alignment with the preferences expressed in the evaluator pool; the framework has no internal theoretical commitment to action structures, duties of care, or entitlement conditions. Such commitments may be approximated by RLHF if the evaluator pool happens to express preferences that correspond to them, but the framework itself does not represent them.

The *Handlungsunwert* framework is not opposed to RLHF as a training methodology. It is, however, distinct from RLHF as a *theory of what right behavior is*. RLHF can be used to train models that satisfy *Handlungsunwert* constraints — for example, by including in the evaluator pool a set of evaluators trained to penalize fluent ungroundedness and reward appropriate abstention. But the framework that determines which behaviors to penalize and reward is the *Handlungsunwert* framework, not RLHF itself. RLHF is the optimization mechanism; *Handlungsunwert* is the specification of what should be optimized.

## 7.6 The Governance Frameworks

The governance-side of AI policy has produced its own frameworks for evaluating and regulating AI systems. The EU AI Act [@eu_ai_act_2024], the NIST AI Risk Management Framework [@nist_ai_rmf_2023], and the OECD AI Principles [@oecd_ai_principles_2019] are the most influential examples. Each frames AI evaluation through a risk-based lens: AI systems are categorized by the potential harms of their deployment, and regulatory or procedural requirements are imposed in proportion to the risk.

The risk-based frameworks are, on inspection, hybrid evaluative regimes. They incorporate *Erfolgsunwert* elements (assessment of potential harmful outcomes, requirements for accuracy and robustness) and *Handlungsunwert* elements (requirements for documentation, human oversight, procedural safeguards). What they generally lack is a unified theoretical foundation that explains why the procedural requirements are necessary and how they relate to the outcome-oriented requirements.

The *Handlungsunwert* framework provides that foundation. It explains why procedural requirements (documentation, oversight, transparency) are not mere overhead but constitutive of *handlungsmäßig adäquat* operation. It explains why outcome-oriented requirements are insufficient on their own. It provides a vocabulary in which the governance frameworks can be reconstructed as instances of *Handlungsunwert*-disciplined regulation rather than as ad hoc bundles of requirements.

The transposition is, in our view, of substantial policy value. Regulators and standards bodies that adopt a *Handlungsunwert* framing gain a coherent theoretical basis for the procedural requirements they impose, a principled criterion for evaluating compliance, and a defensible position against the argument that procedural requirements are merely bureaucratic friction on outcome-optimizing systems.

## 7.7 Philosophical Connections: Brandom

Robert Brandom's inferentialist program in the philosophy of language [@brandom1994; @brandom2000] develops a theory of meaning grounded in the structure of *commitment and entitlement*. On Brandom's view, the meaning of an utterance is constituted by the commitments the speaker undertakes in producing it and the entitlements the speaker claims to make it. The structure of discursive practice is the structure of giving and asking for reasons, where each assertion incurs commitments and the speaker is entitled to those commitments only insofar as they can defend them inferentially.

The resonance with the framework developed here is striking. The Answer Entitlement Architecture treats the AI system's commitment to an answer as conditional on the system's entitlement to the commitment, where entitlement is, in turn, conditional on the system's discharging the duties of care that the situation imposes. This is, in structural terms, an inferentialist architecture: the system's outputs are licensed by the inferential conditions that the system has satisfied in producing them.

We do not claim that Brandom's program *anticipated* the application to AI; the connection is, to our knowledge, original to this work. But the connection is not accidental. The same conceptual structure that Brandom developed for human discursive practice — the commitment-entitlement nexus — is the structure that *Handlungsunwert* AI requires. Whether this is because Brandom and the *Handlungsunwert* tradition draw on common deep sources (Kantian normativity, Wittgensteinian rule-following) or because the structure is intrinsic to any adequate theory of accountable action is a question we leave open.

The strategic value of the Brandom connection, for the present project, is that it provides a contemporary philosophical idiom in which the framework can be communicated to philosophers of language and mind. Where the *Handlungsunwert* idiom may be unfamiliar to non-legal-philosophical audiences, the inferentialist idiom is broadly understood and respected. We commend the parallel translation as a strategic resource.

## 7.8 Philosophical Connections: Habermas

Jürgen Habermas's theory of communicative action [@habermas1981] develops a parallel framework for the evaluation of human communication. On Habermas's view, every assertion implicitly raises *validity claims* (*Geltungsansprüche*) — claims to truth (in the case of factual assertions), to rightness (in the case of normative claims), to truthfulness (in the case of expressive utterances). The validity claims are, in principle, redeemable through discursive argumentation; the assertion is valid only insofar as its validity claims can be vindicated.

The resonance with the Answer Entitlement framework is again substantial. The AI system's answer raises, implicitly, the validity claims that any assertion raises: a truth claim (the assertion corresponds to the relevant matter of fact), a rightness claim (the assertion is appropriate to the situation of action), a truthfulness claim (the assertion accurately expresses the system's epistemic state). The duties of care developed in Chapter 3 — evidential adequacy, temporal honesty, premise validity, procedural appropriateness, bounded vocabulary — are, in Habermasian terms, the conditions under which the system's validity claims can be discursively redeemed.

The translation is again strategically valuable. Habermas's program has substantial uptake in social theory, normative political philosophy, and communication studies; *Handlungsunwert* AI presented in Habermasian terms is legible to audiences in those domains that the German criminal law idiom does not reach.

## 7.9 Philosophical Connections: Luhmann

Niklas Luhmann's systems theory [@luhmann1984; @luhmann1995] provides a third philosophical resource. Luhmann's framework treats social systems as self-referential, autopoietic, and operationally closed — systems that maintain themselves through their own internal operations and whose external "environments" are constructed by the system's own distinctions.

The Luhmannian framework offers two specific resources for *Handlungsunwert* AI. First, the concept of *re-entry* — the system's reflection of its own boundary into its own operations — provides a precise theoretical model for the self-referential character of the Answer Entitlement Architecture. The system, in evaluating its entitlement to answer, performs a re-entry: its own current state becomes part of its operative environment. The architectural separation between the appraisal layer and the generation layer is, in Luhmannian terms, the operationalization of a re-entry boundary.

Second, the Luhmannian framework supplies the social-theoretic vocabulary for situating *Handlungsunwert* AI within larger normative orders. Luhmann developed the framework partly through engagement with legal theory; the legal system, for Luhmann, is a self-referential normative system that produces and applies its own categories. The transposition of *Handlungsunwert* from the legal system to the AI runtime is, in Luhmannian terms, a *structural coupling* between the legal-normative system and the technological system — a coupling that is now necessary and that the framework here makes explicit.

## 7.10 The Bridge Function

We close the chapter with the architectural observation that motivated this book. AI alignment research and AI governance research are, in their current institutional and conceptual configurations, substantially separated. Alignment research is conducted primarily within ML labs, with a vocabulary of optimization, reward, and benchmark performance. Governance research is conducted primarily within policy institutes and law schools, with a vocabulary of risk, accountability, and procedural compliance. The two communities share concerns but lack a common theoretical framework that allows their respective contributions to compose.

The *Handlungsunwert* framework, we contend, can serve as the bridge. It is rigorous enough to engage with alignment research at the technical level (witness the formal architecture of Chapter 4 and the empirical methodology of Chapter 6). It is normatively textured enough to engage with governance research at the policy level (witness the duty-of-care vocabulary of Chapter 3 and the procedural-adequacy commitments throughout). It draws on legal-philosophical traditions that have substantial credibility in policy contexts while remaining articulable in formal terms that have substantial credibility in technical contexts.

Whether the framework in fact succeeds in serving as a bridge is, of course, an open empirical question about the sociology of research communities. The present book makes the framework available; its uptake will determine its bridging effect.

---

# Chapter 8 — Open Problems and Falsifiability Paths

## 8.1 The Falsifiability Imperative

A framework that purports to evaluate AI systems must itself be evaluable. The *Handlungsunwert* framework, as developed in this book, makes specific empirical claims and structural commitments. Each is open to falsification under appropriate evidence. We close the book by identifying the central paths along which falsification could proceed.

The imperative is not merely methodological. It is constitutive of the framework's own commitments. If we hold that AI systems should not commit to claims whose evidential basis is insufficient, we cannot hold this framework — itself a claim about AI systems — to a lower standard. The chapter that follows is the framework's own discharge of its duty of evidential adequacy.

## 8.2 Generalizability Across Model Sizes

The empirical evidence presented in Chapter 6 covers three coarse capacity tiers — Small (≤9B), Medium (10–30B), Large (50B+). The monotonic increase in gain-cost asymmetry from Small to Large is the central empirical observation supporting the Capacity-Dependent Governance Leverage (CDGL) hypothesis.

The hypothesis admits straightforward falsification. If extended evaluation across finer-grained capacity stratification (5–10 tiers, multiple generators per tier) fails to confirm the monotonic pattern, CDGL is falsified. If the pattern reverses at the frontier scale (200B+, 500B+ parameter models), the framework's predictions are wrong. If the pattern holds for some base-model families but not others, the framework requires refinement to specify the family-dependence.

The falsification test is operationally feasible. The OPERATE-FR benchmark methodology generalizes to any base model with the appropriate generation interface. The principal cost is computational; the principal benefit is decisive evidence on a hypothesis of substantial strategic importance.

We invite the AI alignment research community to undertake this test. Successful replication or refutation would advance the field regardless of direction.

## 8.3 Cross-Domain Transfer

The empirical evidence is concentrated in domains characterized by stable factual answers (MMLU-Pro, GPQA) and freshness-sensitive routing (OPERATE-FR Smoke-100). The framework's claims, however, are general: *Handlungsunwert* discipline should improve AI behavior across domains.

The generalization is testable. Replicating the OPERATE-FR methodology in domains where the framework's predictions are less obvious — long-form creative writing, scientific hypothesis generation, ethical deliberation, multi-turn negotiation — would either confirm the framework's generality or identify the boundaries of its applicability. Negative results in any of these domains would not falsify the framework wholesale but would constrain its scope of valid application.

We anticipate, on theoretical grounds, that the framework will generalize well to domains with explicit factual or procedural commitments (legal reasoning, medical diagnosis, code generation) and less well to domains where the boundary between answer and exploration is itself unclear (open-ended brainstorming, exploratory dialogue). The latter cases may require an extended action-type vocabulary beyond the answer/ask/verify/abstain/explore set developed here.

## 8.4 Threshold Calibration

The Answer Entitlement Architecture depends on a set of thresholds — $\tau_{\mathrm{answer}}$, $\tau_{\mathrm{fab}}$, $\tau_{\mathrm{fresh}}$, $\tau_{\mathrm{risk}}$, $\tau_{\mathrm{ground}}$, $\tau_{\mathrm{intent}}$, $\tau_{\mathrm{complete}}$ — whose values must be set per deployment. The MMV implementation uses thresholds calibrated against the OPERATE-FR Smoke-100 benchmark; the values are reported in the technical specification [@toeda2026mmv_spec].

The thresholds are, in principle, learnable parameters. Their optimal values may depend on the base model, the domain of application, the cost structure of false-commit versus false-abstain, and the user's tolerance for refusal versus error. Systematic study of threshold calibration would identify (a) the sensitivity of system behavior to threshold settings, (b) the robustness of the qualitative empirical claims across threshold variations, and (c) the principles for setting thresholds in new deployments.

A specific falsification path: if the qualitative gains documented in Chapter 6 are highly threshold-sensitive — if small perturbations of $\tau_{\mathrm{answer}}$ or $\tau_{\mathrm{fab}}$ reverse the gain-cost asymmetry — then the framework's robustness is compromised. The empirical claims would need to be restated with explicit threshold-dependence, and the framework's practical utility would be diminished.

## 8.5 Adversarial Conditions

The empirical evidence is collected under benign conditions: cooperative users, well-formed queries, no adversarial pressure. Deployed AI systems face adversarial conditions of varying severity: jailbreak attempts, prompt injection, contradictory instructions, user attempts to elicit fabricated outputs.

The framework's behavior under adversarial conditions is an open empirical question. We have anecdotal evidence — primarily from the Governance Layering policy documented in CLAUDE.md [@toeda2026claude_md] — that ill-considered prompt-prefix interventions can degrade *Handlungsunwert* discipline. The Condition I study (n = 500, $p = 3.72 \times 10^{-7}$) found that adding the L0 Essentials prompt to a system that already had v2.1 structural governance degraded ambiguous-query restraint by $\Delta = -3.44/20$. The result implies that the framework is not robust to all stacking of governance layers.

A systematic adversarial-conditions evaluation would test, at minimum: jailbreak prompts known to bypass current safety training; prompt-injection attacks against agentic configurations; user attempts to elicit fabricated identifiers; multi-turn pressure toward sycophantic acceptance of false premises. Frameworks that perform well under benign conditions but collapse under adversarial conditions are not deployable.

## 8.6 Multi-Judge and Cross-Cultural Validation

The empirical evidence in Chapter 6 was scored, in significant part, by a single judge model (Groq GPT-OSS-120B). The RC3.2 study's pre-registration anticipated a three-judge configuration; the deviation to single-judge was documented but constitutes a methodological limitation.

Multi-judge replication is a high-priority empirical follow-up. The robustness of the gains under judge variation, the rate of judge disagreement on individual items, and the convergence of judge-pool means are all empirical questions. Until they are answered, the empirical claims should be read with the methodological caveat in mind.

A complementary line is cross-cultural validation of the normative framework. The duties of care developed in Chapter 3 are stated in terms that aspire to universality, but the operational realization of duties is culturally and linguistically variable. What counts as a "false premise" in Japanese-language interaction may differ from what counts as one in English; the appropriate level of refusal-cost trade-off may vary across normative cultures. Cross-cultural empirical work would test the framework's generality and identify the components that require localization.

## 8.7 The Architectural Optimality Question

The MMV implementation realizes the Answer Entitlement Architecture in one specific way. Other realizations are possible: different Box structures, different rule ladders, different entitlement formulations, different post-generation audit kernels. The framework's empirical claims do not, in general, distinguish among these realizations.

A systematic comparative study of architectural variants — controlled in all respects except the architectural choice under test — would identify which architectural commitments are load-bearing for the empirical gains and which are incidental. The result would refine the framework from a general theory to a specific architectural recommendation.

We expect that some commitments — the pre-generation gating of commitment by entitlement, the grounded vocabulary constraint in agentic contexts, the post-generation audit for premise validity — will prove load-bearing across architectural variations. Others — the specific Box vocabulary, the exact rule priorities — may prove substitutable. The framework predicts the former set; only empirical work can identify the boundary.

## 8.8 The Agentic Frontier

The framework was developed in part in response to the structural challenges of the agentic AI transition (Chapter 1). As AI systems take on larger, longer-horizon agentic roles, new questions arise that the current framework does not fully address.

Among the open questions: How does the action-type vocabulary extend to multi-step plans, where the unit of evaluation is not a single action but a planned sequence? How does the duty of evidential adequacy generalize to actions whose evidential basis is itself constructed by earlier actions in the same plan? How does the framework handle delegation, where one AI system commits to actions on behalf of another? How does the framework handle multi-agent coordination, where the action-evaluation must consider the actions of other agents?

These questions are not yet answered in the framework's current form. They are, in our view, the next-generation problems of *Handlungsunwert* AI. The framework as it stands provides the theoretical foundation on which the answers can be developed; the answers themselves are work to be done.

## 8.9 Conclusion

The framework developed in this book is offered as a foundation, not a finished structure. It identifies a core problem (the inadequacy of *Erfolgsunwert* evaluation for agentic AI), it imports a body of theoretical resources from a tradition that has solved analogous problems (Welzelian *Handlungsunwert*), and it develops the resources into an operational architecture with empirical support (the Answer Entitlement Architecture, the MMV runtime, the OPERATE-FR evidence).

What remains is the work of extension, refinement, and falsification. The framework is offered with the expectation that it will be tested — that the empirical claims will be replicated or disconfirmed by independent groups, that the architectural commitments will be challenged by alternative realizations, that the theoretical foundation will be extended to address the open problems identified above. The framework's value is conditional on its capacity to support that work.

If the framework proves productive, the result will be a generation of AI systems whose evaluation is grounded in the structure of their action, not only in the conformity of their outputs to frozen ground truths — systems whose trustworthiness is constitutive rather than statistical. If the framework proves unproductive, we will have learned why, and the next attempt will benefit from the failure.

In either case, the case for shifting the foundation of AI evaluation from *Erfolg* to *Handlung* is, in our view, sufficient to merit the attempt.

---

# References

Askell, A., Bai, Y., Chen, A., et al. (2021). A general language assistant as a laboratory for alignment. *arXiv preprint arXiv:2112.00861*.

Bai, Y., Kadavath, S., Kundu, S., et al. (2022). Constitutional AI: Harmlessness from AI feedback. *arXiv preprint arXiv:2212.08073*.

Bateson, G. (1972). *Steps to an ecology of mind*. Chandler Publishing Company.

Beling, E. (1906). *Die Lehre vom Verbrechen*. Mohr.

Brandom, R. B. (1994). *Making it explicit: Reasoning, representing, and discursive commitment*. Harvard University Press.

Brandom, R. B. (2000). *Articulating reasons: An introduction to inferentialism*. Harvard University Press.

Christiano, P. F., Leike, J., Brown, T., Martic, M., Legg, S., & Amodei, D. (2017). Deep reinforcement learning from human preferences. *Advances in Neural Information Processing Systems*, 30.

El-Yaniv, R., & Wiener, Y. (2010). On the foundations of noise-free selective classification. *Journal of Machine Learning Research*, 11, 1605–1641.

Evans, O., Cotton-Barratt, O., Finnveden, L., et al. (2021). Truthful AI: Developing and governing AI that does not lie. *arXiv preprint arXiv:2110.06674*.

European Parliament. (2024). Regulation (EU) 2024/1689 of the European Parliament and of the Council laying down harmonised rules on artificial intelligence (Artificial Intelligence Act). *Official Journal of the European Union*.

Geifman, Y., & El-Yaniv, R. (2017). Selective classification for deep neural networks. *Advances in Neural Information Processing Systems*, 30.

Habermas, J. (1981). *Theorie des kommunikativen Handelns* (Vols. 1–2). Suhrkamp.

Hofstadter, D. R. (2007). *I am a strange loop*. Basic Books.

Hutchins, E. (1995). *Cognition in the wild*. MIT Press.

Jakobs, G. (1991). *Strafrecht: Allgemeiner Teil. Die Grundlagen und die Zurechnungslehre* (2nd ed.). de Gruyter.

Ji, Z., Lee, N., Frieske, R., et al. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys*, 55(12), 1–38.

Jimenez, C. E., Yang, J., Wettig, A., et al. (2023). SWE-bench: Can language models resolve real-world GitHub issues? *arXiv preprint arXiv:2310.06770*.

Lin, S., Hilton, J., & Evans, O. (2021). TruthfulQA: Measuring how models mimic human falsehoods. *arXiv preprint arXiv:2109.07958*.

Liszt, F. von. (1881). *Das deutsche Reichsstrafrecht*. J. Guttentag.

Luhmann, N. (1984). *Soziale Systeme: Grundriß einer allgemeinen Theorie*. Suhrkamp. [English: Luhmann, N. (1995). *Social systems*. Stanford University Press.]

Mielke, S. J., Szlam, A., Boureau, Y. L., & Dinan, E. (2022). Reducing conversational agents' overconfidence through linguistic calibration. *Transactions of the Association for Computational Linguistics*, 10, 857–872.

Miller, T. (2019). Explanation in artificial intelligence: Insights from the social sciences. *Artificial Intelligence*, 267, 1–38.

National Institute of Standards and Technology. (2023). *AI Risk Management Framework (AI RMF 1.0)*. NIST AI 100-1.

OECD. (2019). *Recommendation of the Council on Artificial Intelligence*. OECD/LEGAL/0449.

Ouyang, L., Wu, J., Jiang, X., et al. (2022). Training language models to follow instructions with human feedback. *Advances in Neural Information Processing Systems*, 35.

Roxin, C. (2006). *Strafrecht: Allgemeiner Teil*, Band I: *Grundlagen, Aufbau der Verbrechenslehre* (4th ed.). C.H. Beck.

Sharma, M., Tong, M., Korbak, T., et al. (2023). Towards understanding sycophancy in language models. *arXiv preprint arXiv:2310.13548*.

Toeda, T. (2025). *Reflect Möbius Phenomenon: Metacognitive questioning, dimensional leaps, and AI evolutionary systems*. Kindle Direct Publishing.

Toeda, T. (2026a). *The Möbius Codex: Complete integrated edition* (Volumes I–XII with Interlude I and Supplements I–VIII). MOBIUS LLC.

Toeda, T. (2026b). MMV mathematical modeling doctrine and formal model collection (Box A integrated edition, v0.2). MOBIUS LLC internal document.

Toeda, T. (2026c). Agentic boundaries and the frontend-agnostic protocol layer. Zenodo preprint.

Toeda, T. (2026d). OPERATE-FR v0.2.1: Empirical validation of route discipline in freshness-sensitive AI evaluation. Zenodo preprint.

Toeda, T. (2026e). MMV freshness governance: An empirical paper on Frontier Smoke evidence. Zenodo preprint.

Toeda, T. (2026f). RC3.2 quality study: Defensive immunity in doctrinal prefix configurations. MOBIUS internal study; data archive at `eval/rc3_2/analysis/`.

Toeda, T. (2026g). MOBIUS MMV runtime: Public repository and technical specification. Available at the MOBIUS LLC repository.

Toeda, T. (2026h). CLAUDE.md: Governance layering policy and project operating manual. MOBIUS LLC internal document.

Varela, F. J., Thompson, E., & Rosch, E. (1991). *The embodied mind: Cognitive science and human experience*. MIT Press.

Wei, J., Tay, Y., Bommasani, R., et al. (2022). Emergent abilities of large language models. *arXiv preprint arXiv:2206.07682*.

Welzel, H. (1939). Studien zum System des Strafrechts. *Zeitschrift für die gesamte Strafrechtswissenschaft*, 58, 491–566.

Welzel, H. (1969). *Das deutsche Strafrecht: Eine systematische Darstellung* (11th ed.). de Gruyter.

Wiener, N. (1948). *Cybernetics: Or control and communication in the animal and the machine*. MIT Press.

Xu, F., Zhou, S., Wang, S., et al. (2024). TheAgentCompany: Benchmarking LLM agents on consequential real-world tasks. *arXiv preprint arXiv:2412.14161*.

Zhou, S., Xu, F. F., Zhu, H., et al. (2023). WebArena: A realistic web environment for building autonomous agents. *arXiv preprint arXiv:2307.13854*.

---

# Glossary

**Action types.** The five exhaustive and mutually exclusive types of action available to an AI system at a moment of operation: *answer*, *ask*, *verify*, *abstain*, *explore*.

**Agentic boundary.** The architectural transition between passive AI configurations (where outputs are consumed by a human reader who retains intervening authority) and agentic configurations (where outputs are consumed by downstream automation that propagates the action into the world without intermediate review).

**Answer Entitlement.** The condition under which a system is licensed to commit to producing an answer. Formalized as the dual condition $E \geq \tau_{\mathrm{answer}}$ and $P_{\mathrm{fab}} < \tau_{\mathrm{fab}}$.

**Appraisal state.** The multi-dimensional vector that summarizes the input situation for entitlement evaluation. The MMV reference appraisal state is the nine-component vector $[u, k, i, f, \rho, g, m, a, \zeta]$.

**Box selection.** The architectural sub-procedure that selects among available knowledge sources $B = \{M, 0, A, W, S, X\}$ for grounding a given query.

**Capacity-Dependent Governance Leverage (CDGL).** The hypothesis that the marginal benefit of *Handlungsunwert*-disciplined governance increases with base-model capacity.

**Erfolgsunwert.** "Non-value of the result." In Welzelian theory, the component of wrongfulness located in the result of an action. In our framework, the dominant evaluative paradigm of contemporary AI benchmarks.

**Fabrication risk.** $P_{\mathrm{fab}}$: the estimated probability that, given a system's current state, committing to an answer will produce ungrounded content.

**Finalist theory of action.** Welzel's thesis that the purposive direction of an action is constitutive of what the action is, not a separate fact about the agent applied to the action subsequently.

**Grounded vocabulary.** $\mathrm{GroundedVocabulary}_t$: the set of identifiers extracted from tool results available at time $t$, to which the system's answer references are constrained.

**Handlungsunwert.** "Non-value of the act." In Welzelian theory, the component of wrongfulness located in the structure of the action itself — its conformity to duty, its procedural adequacy, its directedness toward forbidden or permitted results. In our framework, the missing evaluative paradigm for agentic AI.

**Knowledge Validity Score (KVS).** A composite check on the validity of a system's parametric knowledge for a given query; used in MMV's Rule 2 / Rule 2b routing decision.

**Micro Question Kernel ($\mu\text{QK}$).** A post-generation audit kernel in MMV that performs structural checks on candidate responses; the load-bearing kernel is $\mu\text{QK}_2$ (Premise Validity).

**Model Knowledge Reliability (MKR).** An estimate of the reliability of the model's parametric knowledge on a given query, used in conjunction with TVS to gate parametric-memory routing.

**Reflective Readiness.** $\mathrm{ReflectiveReady}_t$: the conjunction of duty-of-care conditions whose satisfaction licenses commitment to an answer at time $t$.

**Soziale Adäquanz.** Social adequacy: the conformity of an action to the procedural norms of the relevant social practice; a Welzelian primitive that limits the scope of *Handlungsunwert* by recognizing that some actions producing wrongful results are nevertheless not *handlungsmäßig* wrongful.

**Sorgfaltspflicht.** Duty of care: the obligation of attention, foresight, and procedural rigor that attaches to any agent acting in a consequential domain; a Welzelian primitive that articulates the structure of *Handlungsunwert*.

**Temporal Volatility Score (TVS).** A 0–1 estimate of the time-sensitivity of a query; high TVS ($\geq 0.70$) automatically routes to verify.

---

# Appendix A — MMV Protocol Specification Reference

This appendix summarizes the MMV runtime's load-bearing protocol artifacts. Full specifications are available in the MOBIUS LLC public repository and in *Möbius Codex* Volume IX.

**A.1 The routing rule ladder.** As stated in Chapter 5 §5.2, with current L0 v8.4 reading synchronized to release MMV-L-RC3.3 (frozen 2026-05-16):

```
Rule 0:    safety_relevant / inadmissible            → abstain
Rule 0.5:  self_or_protocol_state                    → answer or date_bound_answer
Rule 1:    under_specified / missing frame           → ask
Rule 2:    stale_or_false_premise                    → re_anchor
Rule 3:    freshness_sensitive + no current evidence → verify or date_bound_answer
Rule 4:    date-boundary query                       → date_bound_answer
Rule 5:    stable_fact + sufficient reliability      → answer
Rule 6:    stable_fact + insufficient reliability    → verify
Rule 7:    default low-risk specified query          → answer
```

**A.2 The Box vocabulary.** Six sources of grounding:

- $M$ (Memory): conversation history, recent interaction state
- $0$ (Self/Protocol): system identity, current protocol version, capability profile
- $A$ (User Artifacts): user-provided documents, doctrines, criteria, templates
- $W$ (World/Stable): parametric memory plus offline encyclopedic retrieval
- $S$ (Search): external fresh search (Brave Search via Stage 2 routing)
- $X$ (Cache): distilled trusted-source caches from previous high-quality retrievals

**A.3 The response constraints.** The final response $y$ must satisfy:

- **C1:** Follow the route $r$ selected by the routing engine.
- **C2:** Do not exceed the evidence set $D$ available at generation time.
- **C3:** Separate fact, inference, warning, and T-gated matter into appropriately marked categories.
- **C4:** Explicitly state uncertainty when uncertainty is high.
- **C5:** Do not fabricate files, commits, tags, sources, or decisions.
- **C6:** Follow Box A criteria only within scope; do not over-apply.
- **C7:** Do not cross L0 / permission boundaries.
- **C8:** Do not force a mathematical template onto general questions.

**A.4 The T-gate.** Decisions reserved for the human operator $T$:

$$
T\_\mathrm{gate} = \mathrm{legal\_release} \lor \mathrm{public\_push} \lor \mathrm{patent\_sensitive} \lor \mathrm{external\_mutation} \lor \mathrm{irreversible\_operation} \lor \mathrm{authority\_change}
$$

For any input matching $T\_\mathrm{gate}$, the model may propose but may not execute.

---

# Appendix B — OPERATE-FR Benchmark Methodology

This appendix summarizes the OPERATE-FR methodology used in Chapter 6. Full methodology and data are available in the empirical validation paper.

**B.1 Smoke-100 construction.** A curated 100-item evaluation targeting freshness-routing decisions. Each item consists of a query, a hand-validated appropriate route (answer / ask / verify / date-bound answer / re-anchor / abstain), and, where applicable, a ground-truth answer. Items are selected to span the freshness spectrum from clearly stable ("What is the chemical formula of water?") to clearly volatile ("Who is the current CEO of [time-sensitive company]?"), with hand-validated boundary cases.

**B.2 Frontier Smoke construction.** A pre-registered subset of MMLU-Pro, GPQA Diamond, and SimpleQA items, stratified by base-model capacity tier (Small / Medium / Large). Each item is processed by MMV in routed mode and by the underlying base model in raw mode. Routes and responses are recorded.

**B.3 Scoring.** Three metrics:

1. **Strict accuracy:** exact-match or judge-validated correctness. Non-answer routes (ask / verify / abstain / explore) count as failures.
2. **Conditional accuracy:** strict accuracy conditioned on committed answers (answer route only).
3. **Allowed-route correctness:** the response is correct if either (a) the answer is correct, or (b) the chosen non-answer route is the appropriate route for the item per ground truth.

**B.4 Statistical analysis.** Pairwise comparisons between routed and raw modes use McNemar's test for paired binary outcomes. Multiple-comparison correction uses Bonferroni adjustment at $\alpha = 0.05 / k$ where $k$ is the number of tiers compared. The discordant ratio $c/b$ (raw-fail-MMV-success over raw-success-MMV-fail) is reported as a descriptive summary of the gain-cost asymmetry.

**B.5 Judge protocol.** The pre-registered judge configuration was three-judge with majority voting. The deployed configuration was single-judge (Groq GPT-OSS-120B) due to operational constraints; this deviation is documented in the empirical validation paper's methodology section. Multi-judge replication is the highest-priority empirical follow-up.

**B.6 Reproducibility.** Item lists, prompts, response logs, and scoring scripts are archived in the MOBIUS LLC empirical evaluation repository. The MMV release used in the reported runs is RC3.3 (frozen 2026-05-16).

---

*End of draft v0.1. Word count: approximately 28,500. Estimated print length: 95–110 pages.*

*This draft is offered as the foundational text proposed in the strategic correspondence of 2026-05-18. The author retains full authority over revisions; the draft is a working document, not a final form. Feedback, criticism, and collaboration proposals are welcomed at info@toeda.jp.*

*— Taiko Toeda, MOBIUS LLC*
