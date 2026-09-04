# Fast-Fail Discovery of Brain-Inspired Plasticity Mechanisms

**Version:** 2.0
**Supersedes:** v1.0, 27 August 2026
**Date:** 4 September 2026
**Instrument:** ARC-AGI-3 offline environments plus purpose-built procedural families
**Cross-domain validation:** active wireless system identification
**Execution mode:** fully autonomous, governed by `AGENT_CONSTITUTION.md`
**Evidence base:** `docs/EVIDENCE_ARC.md` (benchmark), `docs/EVIDENCE_NEURO.md` (science),
`docs/EVIDENCE_TOOLING.md` (the machinery it runs on)

---

## 0. What changed from v1.0, and why

v1.0 was scientifically serious and structurally sound. Nine things in it are now known to be
wrong or unsafe, all of them established by primary sources recorded in the evidence base.
This section exists so the changes are auditable rather than silent.

| # | v1.0 assumption | Finding | Change in v2.0 |
|---|---|---|---|
| 1 | Public ARC performance is a meaningful late-stage validation | Public set saturated at 100.00 RHAE by ≥2 independent systems; ARC states public scores are *"emphatically not a valid measure of progress"* and will never be reported officially | Public games demoted to an integration smoke test and a source of human-efficiency reference data. **v1.0-G9 deleted** — note that v2.0's G9 is a different gate, the M4 campaign. |
| 2 | A mechanism proven on public tasks will transfer | Private set is *"intentionally out-of-distribution relative to the public set"*; ARC measured a harness scoring 97.1% on one environment and 0.0% on another with the same model | External validity now rests on independently-authored held-out generator families, not on ARC splits |
| 3 | The benchmark needs network access and costs money | `OperationMode.OFFLINE`: no key, no rate limit, ~2,000 FPS, unlimited concurrency | **Environment stepping is free and fast.** Model calls remain the binding constraint and are budgeted explicitly — see `docs/EVIDENCE_TOOLING.md` §10 and the G3 cost pre-flight in §9. |
| 4 | Python 3.11 | `arc-agi` requires **Python ≥ 3.12** | Pinned to 3.12 |
| 5 | B4 "executable world model with retrodiction" is a strong baseline | It is the state of the art, and Rodionov's ablation shows replay **verification** is the load-bearing component in all four settings tested | B4 is reclassified as the **reference architecture**. Every mechanism is a delta on top of it. |
| 6 | The human–AI gap on interactive tasks is a plasticity problem | EMPA matches human efficiency on 79/90 novel games with Bayesian theory induction and search and **no plasticity innovation**; frontier reasoning models achieve a 5–11× reduction in discovery inefficiency versus deep-RL baselines with **zero weight updates** (preprint) | **The central thesis is narrowed** (§2). Within-episode efficiency is conceded to priors and inference. The claim is now about what survives *across* episodes. |
| 7 | Localized reconsolidation is established | Rodent input-pathway-specific reconsolidation is solid (Doyère 2007, synapse-resolved). The flagship human result (Schiller 2010) was materially undermined by a verification report finding 61 undisclosed exclusions; the propranolol clinical meta-analysis was rectified to null | Reconsolidation demoted from M1 to M4, narrowed to pathway-scoped unlock, and the adverse literature is cited by us before a reviewer finds it |
| 8 | Astrocytic stabilization (M6) is a candidate mechanism | The abstraction it licenses is a slow per-parameter write-protect register. ML has had that since Benna–Fusi 2016, EWC 2017, Synaptic Intelligence 2017 | **Dropped as a mechanism family.** Retained as one motivating sentence. |
| 9 | Context inference and gating (M4) is a candidate mechanism | Completely covered by BOCPD, mixture-of-experts routing, hypernetworks, task vectors, and Hummos's ICLR 2023 thalamocortical model | **Demoted to infrastructure.** Required by the control plane, claimed as a contribution nowhere. |

### 0.1 Mechanism renumbering, v1.0 → v2.0

The portfolio was reordered on the evidence in `docs/EVIDENCE_NEURO.md`. **Both that document
and any note you wrote against v1.0 use the old numbers.** This table is the only mapping;
where anything disagrees with it, this table governs.

| v1.0 | v1.0 name | v2.0 | v2.0 status |
|---|---|---|---|
| M1 | Inhibitory memory **+ localized reconsolidation** | **split in two** | inhibition → **M1** (centrepiece); reconsolidation → **M4** (conditional) |
| M2 | Uncertainty-triggered compositional **preplay** | **M3** | narrowed; the word *preplay* is deleted |
| M3 | Event-triggered fast causal binding | **M2** | reframed as gated one-shot write |
| M4 | Rapid latent-context inference and gating | — | **demoted to infrastructure**, claimed nowhere |
| M5 | Dendritic conjunctive microcircuits | **M5** | reserve, unchanged |
| M6 | Slow plasticity governor (astrocytic) | — | **dropped** |

**Gate numbers are also fresh.** v2.0's G0–G12 are not v1.0's. Where v1.0's gates are meant,
they are written `v1.0-G9`. In particular v2.0's **G9 is the M4 campaign**, and it is *not*
related to v1.0-G9, which was deleted.

### 0.2 Two additions

**RHAE** as a first-class metric with its 5× human-median action-budget termination rule (§8),
and an **MIT-0 licence from the first commit** (a
permissive public-domain licence is the only one that would ever satisfy ARC's prize terms,
and it is free to adopt now and painful to retrofit).

---

## 1. Objective

Discover whether one or more isolated plasticity-control operations produce a reliable,
compute-matched improvement in an agent's ability to **retain, protect, suppress and recompose
causal knowledge across episodes** — and whether any such operation constitutes a reusable
learning primitive that transfers to an unrelated interactive domain without redesign.

The objective is not a benchmark score. ARC-AGI-3 is the instrument, chosen because it
supplies interactive environments with hidden causal structure, an official action-efficiency
metric measured against humans, 342 human action-by-action replays, and free unlimited offline
execution. Any of those could be replaced; the mechanism question could not.

---

## 2. The central thesis, narrowed

v1.0 proposed:

> Flexible intelligence may require a separate plasticity-control system that decides when an
> AI should retrieve, simulate, suppress, revise, rapidly bind, consolidate, protect or roll
> back knowledge during inference.

That claim, as stated, is now contradicted by the best available measurements. Two results in
particular:

- **Tsividis et al. (2026)**, *Phil. Trans. R. Soc. A* 384:20240529. 300 participants, 90
  novel video games. EMPA — Bayesian theory induction in a compositional model class, plus
  theory-driven exploration, plus best-first planning — matched human learning efficiency on
  **79 of 90 games**, while DDQN was more than 100× less efficient on 67 of 90 and more than
  10,000× worse on 22. EMPA contains **no plasticity innovation at all**.
- **Csaba et al. (2026)**, arXiv:2605.08019, preprint. Frontier reasoning models achieved a
  5–11× reduction in discovery inefficiency relative to deep-RL baselines on novel games with
  **zero weight updates**, and predicted human fMRI BOLD an order of magnitude better than RL
  alternatives.

The honest reading is that **structured priors and in-context inference, not plasticity,
explain most of human within-episode sample efficiency.** A proposal that ignores this is
proposing a cure for a disease that is largely already treated.

The defensible thesis, and the one this project tests, is narrower:

> **Priors and in-context inference explain how fast an agent learns within an episode. They
> do not explain what survives across episodes. Cross-episode retention, interference
> management, and the conversion of in-context discoveries into durable composable skills are
> plasticity-control problems, and no current system solves them.**

This is not a retreat. It is a sharper target, and it has a decisive methodological
consequence:

> **Every experiment in this project must be constructed so that in-context learning cannot
> substitute for a change in persistent state.** Concretely: horizons that exceed the working
> context, sequential curricula with interference between separately acquired mechanisms, and
> evaluation of environment *k* after environments *1…k−1* have been learned and the context
> has been cleared. An experiment that a frozen model, given the whole transcript inside its
> context window, would pass is not a test of this thesis and does not count. The operational
> form of that test is gate predicate `G-CTX` in §9, G4, which compares against the project's
> maximum context rather than an unrealisable unbounded one.

This constraint is enforced mechanically. See §9, gate predicate `G-CTX`.

---

## 3. What would count as field-defining

A candidate must demonstrate most of the following. Items marked **▲** are new in v2.0 and
follow directly from the narrowed thesis.

1. **Cross-episode persistence ▲** — learning in environment *j* measurably improves
   environment *k > j* after the context is cleared.
2. **Interference control ▲** — acquiring mechanism B does not degrade mechanism A beyond a
   pre-registered tolerance.
3. **Context-clearing invariance ▲** — the advantage survives when the in-context transcript
   is discarded between episodes and only the persistent state carries forward.
4. **Selective revision** — incorrect knowledge changes without erasing unrelated correct
   knowledge.
5. **Controlled suppression** — the agent stops repeatedly retrieving a misleading analogy,
   without losing the ability to retrieve it where it is correct.
6. **Action efficiency** — more useful information per real environment action, measured in
   RHAE against the human baseline.
7. **Unseen mechanism-family generalization** — works on causal rule families absent from
   development, generated by code the agent never saw.
8. **Compositional reuse** — previously learned mechanisms recombine in new environments.
9. **Calibrated uncertainty** — confidence corresponds to predictive reliability.
10. **Reversibility** — harmful updates are detected and rolled back.
11. **Compute-matched advantage** — the effect survives matching model calls, simulations,
    tokens and environment actions.
12. **Mechanism-specific ablation** — removing the proposed operation removes the targeted
    behaviour and nothing else.
13. **Cross-domain transfer** — the same core operation improves active wireless system
    identification with only input, output and primitive adapters changed.

---

## 4. Mechanism portfolio, reordered by evidence

v1.0 ordered mechanisms by implementation cost. v2.0 orders them by **(evidence strength) ×
(gap versus what machine learning already has)**, which is the only ordering that can produce
a field-defining result. The ranking is derived in `docs/EVIDENCE_NEURO.md`.

| Rank | Mechanism | Empirical support | Gap vs. ML | Status |
|---|---|---|---|---|
| **M1** | Context-conditioned inhibitory suppression | Strong–moderate | **Large** | **Centrepiece** |
| **M2** | Gated one-shot write (BTSP, reframed) | Strong in CA1, weak elsewhere | Moderate–large **if reframed** | Primary |
| **M3** | Priority-gated selective and compositional replay | Strong for selection and recombination; **weak for preplay** | Moderate | Primary, narrowed |
| **M4** | Retrieval-gated scoped unlock (reconsolidation) | Rodent good, human damaged | **Small** | Conditional, heavily caveated |
| M5 | Dendritic conjunctive microcircuits | — | — | Reserve, compact unit test only |
| — | Context inference and gating | Strong | **~Zero** | **Infrastructure, not a contribution** |
| — | Astrocytic slow stabilization | Moderate, real confounds | **Negative** | **Dropped** |

### M1 — Context-conditioned inhibitory suppression  *(centrepiece)*

**Targeted failure.** The agent continues retrieving an attractive but falsified analogy; a
schema that is correct in context A is applied in context B where it is wrong; suppressing it
in B destroys its usefulness in A.

**Biological observation, separated from the abstraction.**
- Liao et al. (2024), *Nat. Neurosci.*, DOI 10.1038/s41593-024-01745-w. Awake behaving mice,
  optogenetics plus three-level modelling. Salient stimuli were either recruited into **or
  actively suppressed from** sharp-wave ripples; a Hebbian STDP rule *at inhibitory synapses*
  parsimoniously explains the selectivity. Critical test: artificially implanted
  non-generalizable representations **accumulated inhibition during ripples**, as predicted.
  Inhibition performing a computation, with a causal test.
- Wimber et al. (2015), *Nat. Neurosci.* 18:582–589, DOI 10.1038/nn.3973. Human fMRI with
  MVPA. The **cortical pattern of the competing memory specifically** is suppressed across
  repeated selective retrievals, and the degree of suppression predicts later forgetting of
  that competitor. Targeted at a representation, not global gain.
- Barron et al. (2017), *PNAS* 114:6666–6674 — the theoretical form: a matched, memory-specific
  inhibitory trace that **silences rather than erases**.
- Wu et al. (2026), *Nat. Neurosci.*, DOI 10.1038/s41593-026-02235-x. NPY⁺ interneurons use
  fast GABAergic inhibition for acquisition and **slow NPY-mediated inhibition for
  extinction**, via two non-overlapping receptor-defined populations. Two inhibitory timescales
  with distinct targets.

**Computational abstraction.** A learned negative-key memory in the same representational
space as the excitatory trace:

```
score(q | c) = ⟨q, W_E⟩  −  g(c) · ⟨q, W_I⟩
```

with `W_I` learned by a Hebbian rule at inhibitory synapses driven by co-activation during
competition; `g(c)` a context gate, so the same trace is retrievable in one context and silent
in another; suppression **subtractive and matched in the representation**, not multiplicative
gain; and the trace **reversible** — silent, not erased. Two masks, fast and slow.

**Why this is the centrepiece.** Machine learning has no principled, learned,
context-conditioned, *reversible* suppression of a specific memory. Machine unlearning is
destructive and leaky. Activation steering and SAE feature clamping are hand-specified, not
learned. There is no inhibitory engram learned by the same competitive dynamics that created
the excitatory one. This is the largest gap identified anywhere in the evidence base.

**Strong controls that must be beaten.** Vogels–Sprekeler inhibitory plasticity (2011 — the
computational form already exists and is fifteen years old); hard context-tagged blacklist;
Bayesian posterior decay; machine unlearning by gradient ascent on a forget set; hand-specified
activation steering; retrieval score penalty by hard-negative mining.

**Known cost, which must be measured.** Hulbert et al. (2016), *Nat. Commun.* 7:11003 —
retrieval stopping produces a temporal amnesic shadow for unrelated events. **Suppression is
not free.** The experiment must measure collateral loss, not only the intended suppression.

**Adverse literature the project must confront itself.** The physiological and rodent evidence
above is causal and strong; the *human behavioural* effect is small, and a reviewer who knows
this literature will say so first. Bulevich et al. (2006), *Memory & Cognition* 34:1569, failed
to find suppression-induced forgetting. A multiverse analysis of early think/no-think
replication attempts (*Memory*, 2020, DOI 10.1080/09658211.2020.1797095) is standard opposing
ammunition — **this one was not retrievable during compilation and must be read before it is
cited.** Against those: a pre-registered replication (*Memory*, 2023,
DOI 10.1080/09658211.2023.2208791) and Niczyporuk (2025), *Psychon. Bull. Rev.*,
DOI 10.3758/s13423-025-02763-w, which concludes from two meta-analyses that the effect is
**small-to-moderate but reliably replicable in healthy participants, and not significant in
clinical or subclinical samples**. The honest position: the phenomenon survives, the human
effect size is small, and the project's claim rests on the computational gap plus the causal
rodent evidence — not on the size of the human behavioural effect. Do not oversell it.

**Pass rule** (pre-registered; this is the single place M1's criteria are defined, and §9 G6
refers here rather than restating them): ≥25% fewer repeated false-schema actions; ≥95%
retention of unaffected rule accuracy; **context-specificity index CSI ≤ 0.2** as defined in §8
— that is, suppression in the wrong context is at most 20% of suppression in the right one; no
more than the pre-registered collateral-forgetting tolerance; and the advantage must survive
against **B9** (Vogels–Sprekeler), **B10** (unlearning and steering) and **B13**
(context-tagged blacklist).

**Kill rule:** a context-tagged blacklist matches it; suppression is not reversible in
practice; collateral forgetting exceeds tolerance; or the learned `W_I` is not measurably
different from a hand-specified negative key.

### M2 — Gated one-shot write  *(BTSP, reframed)*

**The reframing is the whole point.** If this is framed as "eligibility trace plus instructive
signal", it is e-prop (Bellec et al., *Nat. Commun.* 2020) and RFLO (Murray, *eLife* 2019), and
the claim fails immediately. Roughly 70% of BTSP is already held by machine learning.

What is not held:
1. The gate is a **learned, per-unit, sparse, structured decision** — an inference that *this
   input is worth binding now*, computed from conjunctive top-down input, not a broadcast
   scalar reward.
2. **Postsynaptic independence, weight dependence, binarity.** Wu & Maass (2025), *Nat.
   Commun.* 16:342, DOI 10.1038/s41467-024-55563-6: stochastic BTSP on binary weights, flip
   probability 0.5 within a 10 s window, dependent on presynaptic activity and prior weight
   only. One-shot storage at 0.5% activation sparsity, tolerant of 30% pattern overlap and 1/3
   masked bits; instant recall against ~100 iterations for Hopfield; uniquely reproduces the
   human repulsion effect. The authors state explicitly that BTSP is *"not just a variant of
   STDP on a longer time scale."*
3. **The gate rate is itself under control.** Madar et al. (2025), *Nat. Neurosci.*,
   DOI 10.1038/s41593-025-01894-6: BTSP, not STDP, best explains place-field shifting;
   induction events are rare, **increase in novelty**, and their probability decays after field
   onset. The gate is regulated — which is the thesis.

**Therefore M2 is stated as:** *learned sparse write-gating over a binary content-addressable
store, with gate rate under novelty and uncertainty control.* **The novel object is the gating
policy, not the plasticity rule.**

**Evidence hygiene.** Canonical BTSP is Bittner et al. (2017), *Science* 357:1033. The cortical
extension is a **preprint** (bioRxiv 10.1101/2025.11.07.687250), layer-5 restricted, with a
markedly narrower and asymmetric window (−2 s to +0.5 s versus CA1's ±5 s). **There is no human
BTSP evidence. The proposal must not imply otherwise.**

**Strong controls:** e-prop; RFLO; three-factor rules; conventional fast weights (Ba et al.
2016); online gradient descent; recursive least squares; exact episodic retrieval; and — the
decisive one — **the same store with a random or fixed-rate gate**, which isolates the policy
from the substrate.

**Pass rule:** learns the delayed association in one or very few episodes; transfers to new
surface instances of the same mechanism; exceeds exact episodic retrieval on *compositional
reuse* specifically; remains stable under irrelevant surprise; and **beats the same store with
a random gate at matched write count** — this last is the only comparison that tests the claim.

### M3 — Priority-gated selective and compositional replay

**Narrowed from v1.0's "uncertainty-triggered compositional preplay".** The word *preplay* is
deleted. Rodent preplay is an unresolved fight — Dragoi & Tonegawa (2011) against Silva, Feng &
Foster (2015), partially split by Grosmark & Buzsáki (2016) — and the project does not need to
enter it, because a better-supported human result exists.

**Build on:** He et al. (2026), *Nat. Neurosci.*, DOI 10.1038/s41593-026-02291-3. Human iEEG,
28 patients, simultaneous hippocampal and cortical recording, relational inference tasks.
Ripple-locked replay **reorganised familiar building blocks into candidate novel sequences**;
mPFC shifted toward inferred relational configurations around ripples; ripple-locked replay
strength predicted inferential efficiency. Compositional recombination, in humans, measured
directly, peer-reviewed.

**Supporting:** Yang et al. (2024), *Science* 386:1478 — awake ripple content predicts sleep
replay content at R = 0.86, the cleanest evidence that ripples act as a **tagging and selection
operator** rather than a uniform rehearsal buffer. Frank et al. (2026), *Nat. Neurosci.*,
DOI 10.1038/s41593-026-02345-6 — human iEEG, 2,728 ripples; **pre-stimulus** ripple rate and
duration rise with entropy, peaking 800–400 ms before stimulus onset. Uncertainty gating, in
humans, prospectively.

**Two operators, not one.** The data license a **selection/tagging** operator and a
**recombination** operator, and they are dissociable — Widloski & Foster (2025) found 20–24% of
replays had neither ripples nor population bursts. They must be implemented and ablated
separately.

**Adverse literature the project must confront itself.** Deceuninck & Kloosterman (2024),
*eLife* 13:e84004 — closed-loop awake-ripple disruption across three spatial memory tasks found
**no significant effect**, contradicting the standard reading of Jadhav et al. (2012).
Thompson et al. (2026), *Nat. Neurosci.* — striatal replay and learning **fully intact after
hippocampal ablation**; replay is a generic circuit motif, so "the hippocampus does it" is not
an argument. Takigawa et al. (2024), *eLife* 13:e85635 — no ground truth exists for replay
detection; nominal α = 0.05 corresponds to actual false-positive rates of 2–18% depending on
shuffle procedure.

**The hardest control.** Mattar & Daw (2018), *Nat. Neurosci.* 21:1609 already gives the
normative theory — Expected Value of Backup, gain × need — and it already fits rodent and human
replay data. **A reviewer will say M3 is EVB with new names.** M3 must therefore be run against
an explicit EVB implementation, and its pass rule requires beating EVB, not merely beating
uniform replay. Prioritized Experience Replay is the weaker floor.

**Pass rule:** reduces real actions by ≥20% at matched total simulation count; **beats an
explicit EVB baseline** on compositional-reuse environments specifically; the recombination
ablation removes the compositional advantage while leaving the selection advantage intact.

### M4 — Retrieval-gated scoped unlock  *(conditional)*

**Demoted from v1.0's M1 and narrowed to one grain size.**

**What is supported:** Doyère et al. (2007), *Nat. Neurosci.* 10:414–416. Rats; two independent
auditory input pathways to lateral amygdala, each conditioned to a different CS. Retrieval of
one CS produced potentiation **selective to the reactivated pathway**, and reconsolidation
blockade reduced potentiation **only at those synapses**. Input-pathway-specific, measured at
the synapse, unimpeached. **This is the citation M4 rests on.**

**What is not supported, and must be said by us first:** arbitrary component-level editing of
rich human memories. Schiller et al. (2010), *Nature* 463:49 — the flagship human result — was
materially undermined by Chalkia, Van Oudenhove & Beckers (2020), *Cortex* 129:510, a
verification report on the original data finding **61 actual exclusions against 6 reported**,
mismatched analyses, and all reported differences contingent on unprincipled qualitative
exclusions. The propranolol clinical meta-analysis was **rectified to null** (*J. Psychiatry
Neurosci.* 2022, DOI 10.1503/jpn.220072-l). A boundary-condition replication failed (*Sci. Rep.*
12, 2022).

**Therefore M4 assumes pathway-scoped unlock and says so explicitly**, and every document that
cites Schiller cites Chalkia in the same sentence.

**The contribution is the trigger, not the edit.** ROME and MEMIT already perform
causally-scoped localized editing with better precision than the biology supports. What machine
learning lacks is the **principled decision to unlock and the automatic relock**. The criterion
comes from Gershman et al. (2017), *eLife* 6:e23763 — the latent-cause account of when
reconsolidation occurs versus when a new trace is formed — combined with Sevenster, Beckers &
Kindt (2013), *Science* 339:830, which established prediction error as necessary for
destabilization:

```
on retrieval of trace T with prediction error δ:
    if δ_low < δ < δ_high:          # too little, no unlock; too much, spawn a new trace
        unlock(scope(T, cue))        # scope = the reactivated pathway only
        bounded_update(window W)
        relock(T)
```

**M4 runs only if M1 produces a signal**, because a scoped unlock without a working suppression
operator has nothing to protect the unaffected components.

### M5 — Dendritic conjunctive microcircuits  *(reserve)*

Unchanged from v1.0 and unchanged in status: a compact architectural unit test, run only if
measured relational-binding failures justify it, killed immediately if a parameter-matched
conventional architecture matches sample efficiency and transfer.

### Infrastructure — context inference and gating  *(not a contribution)*

Required by the control plane to condition M1's suppression masks and to make M4's
unlock-versus-new-trace decision. Claimed as a contribution nowhere, because BOCPD (Adams &
MacKay 2007), mixture-of-experts routing, hypernetworks, task vectors, and Hummos's ICLR 2023
thalamocortical "Thalamus" model cover the abstraction completely.

Two results are used as **design constraints** rather than claims. Zhang et al. (2025), *Nat.
Commun.*, DOI 10.1038/s41467-025-58011-1: restricting plasticity to the thalamocortical
interface alone still supported rapid context switching, while ~80% of MD units encoded context
and 55–65% of PFC units showed context-invariant rule tuning. This justifies implementing the
control plane as a **low-rank adapter over frozen shared parameters**. Foucault et al. (2026),
*eLife* reviewed preprint, DOI 10.7554/eLife.110137.1: humans detect a variance change within
**~3 observations**. This is the latency target the context module is held to.

### Dropped — astrocytic slow stabilization

The evidence is respectable: Williamson et al. (2025), *Nature* 637:478 and Dewa et al. (2025),
*Nature*, DOI 10.1038/s41586-025-09619-2, with a genuine multiday molecular window (*Adrb1* and
*Adra1a* upregulated 1–3 days, peaking at day 1, effector IGFBP2). It is dropped anyway,
because the abstraction it licenses is a slow per-parameter write-protect register and machine
learning has had that since Benna & Fusi (2016), EWC (2017) and Synaptic Intelligence (2017).
Adding it buys biological novelty and zero computational novelty while importing real
liabilities: astrocytic Gq-DREADD non-specificity, Fos-tagging temporal coarseness, a novelty
confound the authors themselves flag, freezing-only readout, and fear memory only.

Retained as one sentence of motivation for the write-schedule module: *a slow, separately
gated, neuromodulator-triggered process determines whether a recalled memory is re-stabilized.*

### Structural change: primitives are not all the same kind of thing

v1.0 listed eight coequal operations. Four of them — RETRIEVE, PREPLAY, SUPPRESS, FAST_BIND —
are inference-time operations with direct neural correlates. Four — CONSOLIDATE, PROTECT,
DESTABILIZE, ROLLBACK — are offline scheduling operations that machine learning already has
under other names (EWC, Synaptic Intelligence, model editing, checkpointing).

v2.0 collapses the second group into a single **write-schedule** module that is explicitly not
a contribution, and spends the recovered effort on the **gating policy** that selects among the
first group — because the policy, not the primitives, is the part nobody has.

---

## 5. Laboratory architecture

Unchanged from v1.0 in outline; three components are added or hardened.

- **Observation layer.** Raw grid, object-and-relation representation, transition delta. Early
  experiments bypass visual parsing entirely so perception errors cannot masquerade as learning
  failures.
- **Immutable episodic store.** Exact states, actions, outcomes, timestamps, object changes,
  predictions, prediction errors, confidences. Indexed, never destructively rewritten.
- **Reference architecture (was B4).** A verified executable world model: induce Python that
  simulates the environment, **backtest it against the complete transition history**, plan
  inside the certified model, abandon the plan and repair on prediction mismatch, refactor
  toward simpler abstractions. Rodionov's ablation identifies verification as load-bearing;
  this component must be built to a competitive standard or all downstream comparisons are
  void. Its quality is itself a gate exit condition (§9, `G3`).
- **Persistent-state boundary ▲ (new).** An explicit, serialisable object that is the *only*
  thing carried between episodes. The in-context transcript is discarded at every episode
  boundary in every cross-episode experiment. Its size is capped and matched across conditions.
  This is the mechanism that makes §2's constraint enforceable rather than aspirational.
- **Replaceable mechanism slot.** Common interface, unchanged:
  ```python
  class PlasticityMechanism(Protocol):
      def observe(self, transition: Transition) -> None: ...
      def propose_operation(self, state: AgentState) -> PlasticityOperation: ...
      def apply(self, op: PlasticityOperation, state: AgentState) -> AgentState: ...
      def diagnostics(self) -> dict[str, float | int | str]: ...
  ```
- **Provenance layer.** Every run records code commit, generator commit, config, seed,
  dependency lock hash, hardware, model identifier, prompt hash, action history, simulation
  count, wall-clock, token use, results, artifact hashes.

---

## 6. Diagnostic environment families

Families A–L from v1.0 are retained. Their **priority order changes** to match the narrowed
thesis: families that test cross-episode retention and interference move to the front, because
those are the only ones that can discriminate plasticity from in-context inference.

**Tier 1 — build first. These test the actual thesis.**

| Family | Tests | Why it is tier 1 |
|---|---|---|
| **E** Local rule change | Selective revision without full-model destruction | Interference, not speed |
| **I** Context recurrence | A rule disappears and later returns | Requires persistent state across a context clear |
| **L** Multi-timescale change | Slow stable rules versus fast contextual ones | Directly separates the two stores |
| **J** Distractor memory | Many superficially similar irrelevant episodes | Retrieval interference at scale |
| **F** Compositional mechanisms | A and B learned separately, then B∘A unseen | Cross-episode composition |

**Tier 2 — build second.**

| Family | Tests |
|---|---|
| **G** Deceptive familiar analogy | Suppression of attractive false schemas — M1's primary target |
| **D** Delayed causality | Temporal credit assignment — M2's primary target |
| **A** Action-semantic discovery | Rapid system identification |
| **H** Irreversible experiments | Risk-sensitive active experimentation |

**Tier 3 — build only if needed.** B counterfactual visual twins, C mechanism twins,
K partial observability.

**Requirements unchanged for every generator:** seeded generation, exact replay, symbolic and
visual modes, mechanism-level train/validation/held-out splits, and an oracle model.

**Requirement added ▲:** every tier-1 family must ship a **context-clear variant** in which
the agent's transcript is discarded between episodes and only persistent state survives. A
family without this variant cannot be used for a mechanism verdict.

**Held-out generators.** v1.0's rule stands and is strengthened: held-out generator source code
must never be read by the agent, and held-out families must be *independently authored* — a
different generation strategy, not a reparameterisation. The autonomous agent generates
held-out families in a session that has no access to the development generators, and the
resulting code is hash-locked before any mechanism is run against it.

---

## 7. Baseline ladder, revised

| | Baseline | Purpose | Change |
|---|---|---|---|
| B0 | Random legal action | Trivial floor; detects task leakage | — |
| B1 | Systematic graph exploration | Can disciplined enumeration solve it? | **Promoted.** Rudakov et al. (arXiv 2512.24156) ranked 3rd on the private preview leaderboard with training-free graph exploration and no LLM, *"substantially outperforming frontier LLM-based agents."* This is a serious baseline, not a floor. |
| B2 | Immutable episodic memory | Isolates the value of raw evidence | — |
| B3 | Bayesian / score-based hypothesis tracker | Does the mechanism reduce to ordinary model selection? | — |
| **REF** | **Verified executable world model** | The reference architecture | **Reclassified from B4.** Not a baseline — the substrate every mechanism is added to. |
| B5 | Fixed-budget replay | Separates better timing from more computation | — |
| B6 | Standard online adaptation (SGD, RLS, RNN state, fast weights) | Is the rapid plasticity rule distinct? | — |
| B7 | Fixed memory rewrite | Selective reconsolidation against ordinary consolidation | — |
| **B8** | **EVB (Mattar & Daw 2018)** | The normative replay theory | **New and mandatory for M3.** |
| **B9** | **Vogels–Sprekeler inhibitory plasticity (2011)** | The fifteen-year-old computational form of M1 | **New and mandatory for M1.** |
| **B10** | **Machine unlearning and activation steering** | The live ML analogues of targeted suppression | **New and mandatory for M1.** |
| **B11** | **ROME / MEMIT scoped editing** | Already does localized editing | **New and mandatory for M4.** |
| B12 | Strong LLM agent | Does the mechanism still matter with strong semantic priors? | Retained, **but reclassified as a research probe, never a deliverable** |
| **B13** | **Context-tagged blacklist** | The trivial version of context-conditioned suppression | **New and mandatory for M1.** It is also M1's kill condition — if this matches M1, M1 dies. It must therefore exist as code, not as a rhetorical foil. |

**Rule, unchanged and non-negotiable:** a mechanism cannot pass unless it beats the strongest
appropriate baseline in this ladder. v2.0 adds four baselines specifically because the evidence
base identified them as the methods a reviewer will say the mechanism reduces to.

---

## 8. Metrics

v1.0's metric set is retained. Four things are added.

**RHAE ▲.** The official metric, implemented exactly as specified in `docs/EVIDENCE_ARC.md` §2:
squared ratio, cap **1.15** inside the min, level weight `w_l = l`, completion cap, plain mean
over environments. The **5× human-median action budget** termination rule applies in the
laboratory as well, so laboratory efficiency numbers are commensurable with published ones.

**Cross-episode metrics ▲.** Forward transfer, backward transfer, catastrophic forgetting, and
**retention-after-context-clear** — accuracy on environment *j* measured after environments
*j+1…k* have been learned and the transcript discarded.

**Suppression metrics ▲.** **Context-specificity index, CSI = (suppression measured in the
wrong context) / (suppression measured in the right context).** Lower is better: CSI = 0 is
perfectly context-specific suppression, CSI = 1 is a context-blind blacklist. The pass
threshold is **CSI ≤ 0.2**. `verify_run.py` implements this formula and this direction; nothing
else in the project may define CSI. Also: collateral forgetting on unrelated material, and
suppression reversibility (recovery of a silenced trace when its context returns).

**Gate-policy metrics ▲.** For M2, the write-gate rate, its correlation with novelty and
uncertainty, and performance against a random gate at matched write count.

**Statistics unchanged:** paired bootstrap confidence intervals, effect sizes, per-environment
results, medians and tail behaviour. Not aggregate averages alone.

---

## 9. Gates, with machine-checkable exit predicates

This is the structural change that makes autonomy possible. In v1.0, gate exit conditions were
prose a human judged. In v2.0 **every exit predicate is either evaluated by a script or names
the specific artifact a referee must inspect** — never left as prose for the working agent to
interpret about itself. `scripts/verify_run.py` implements the script-evaluable ones and reads
every numeric threshold from the gate's hash-locked `preregistration/<gate>.yaml` rather than
from this table, so a threshold exists in exactly one machine-readable place. Its own hash is
pinned. Verdicts are issued by a referee process, and a verdict that does not cite artifact
paths and SHA-256 digests is rejected mechanically.

**Gate completion is not mechanism success.** These are different things and conflating them
deadlocks the ladder. A **mechanism gate closes** when a referee verdict in
`{GO, REVISE_ONCE, KILL, SUSPEND_FOR_DEPENDENCY}` exists, cites hashes, and records the
pass-rule evaluation. The **pass rule** decides only whether that mechanism enters G10, not
whether the gate closes. A KILL therefore closes its gate and the ladder continues — which is
what makes "a negative result is a result" true in the machinery and not only in the prose. A
conditional gate whose trigger never fires is marked `gate_status: "skipped"`, which counts as
satisfied for entering its successor.

| Gate | Work | Exit predicate (all must be true) |
|---|---|---|
| **G0** Bootstrap | Repository, environment, lockfile, lint, type check, tests, seeds, smoke experiment, first commit | `uv sync` from clean clone exits 0 · `pytest` exits 0 with ≥1 test · ruff and mypy exit 0 · **`results.json` and `metrics.csv` are byte-identical across two seed-fixed invocations after excluding the fields named in `configs/nondeterministic_fields.yaml`** (run id, timestamps, wall-clock, host — the manifest necessarily differs, so whole-artifact identity is the wrong test) · every hash in `SHA256SUMS` verifies against its file · `git status --porcelain` empty · LICENSE is MIT-0 · every `[VERIFY-ON-MACHINE]` item in `docs/EVIDENCE_TOOLING.md` §11 is resolved and written back |
| **G1** ARC interface | Install `arc-agi`, warm the environment cache, then run and replay entirely offline | `arc-agi` version pinned in `uv.lock` · **step 1: a cache-warming run downloads environment files for the 25 public games and records their hashes** (the first `OFFLINE` instantiation needs the network — the cache starts empty) · **step 2: a subsequent `OperationMode.OFFLINE` run completes with zero network calls, asserted by a socket guard** · ≥1 public game runs to a terminal state · recorded trajectory replays to an identical final frame · measured throughput ≥ 500 FPS |
| **G2** Human baseline | Ingest the 342 replays; derive per-level human action baselines; implement RHAE | **RHAE passes a synthetic-vector test: 6–8 hand-computed cases exercising the 1.15 cap, the `w_l = l` weighting, the completion cap, and a case that distinguishes `min(1.15,(h/a)²)` from the superseded `min(1.0,h/a)²`** — reproducing a published 100.00 score proves nothing, since any capped implementation reaches it · human baselines derived for ≥80% of the 183 public levels · **the replay dataset is obtained** — its canonical location is UNCONFIRMED (`EVIDENCE_ARC` §6 item 6), so acquisition is a **bootstrap-stage human task**, with `huggingface.co/datasets/zarczynski/arc-agi-3-public` as the named fallback; if neither yields the replays, escalate immediately under constitution §6 item 11 rather than climbing the ladder |
| **G3** Reference architecture | Build the verified executable world model to competitive standard | **Cost pre-flight first: build REF, measure consumption on 3 games, extrapolate to 25, and escalate under constitution §6 item 10 if the projection exceeds the pre-registered fraction of the weekly allowance.** Then: REF scores ≥ 55% RHAE on the 25 public games. **This is an engineering-quality bar on the substrate, not evidence of progress** — the public set is disavowed as a progress measure (§0 row 1) and is used here only to establish that the substrate is competently built. The 55 floor is the lower published figure (Rodionov 58.12%, GPT-5.5) minus a 3-point implementation margin; OPINE-World's 78.4% used a different model and is not the target · replay verification demonstrably active: an injected wrong model is rejected by backtesting in ≥95% of seeded trials · runs offline after cache warming |
| **G4** Diagnostic families, tier 1 | Families E, I, L, J, F with oracles, splits, and context-clear variants | Every generator passes its oracle test · **determinism: each of 3 seeds re-run twice produces identical output within a seed, and different output across seeds** · **`G-CTX`, corrected: a frozen-model control at the project's maximum context, run on the family's context-clear variant, must not exceed the persistent-state-ablated agent by more than δ on the family's primary metric, where δ and the metric are named in the family's generator config and δ is pre-registered.** (v2.0's first draft said "unbounded context" and "no better than chance"; neither is realisable — no unbounded context exists, and "chance" is undefined for an interactive game under a 5× action budget. The comparative form is what the thesis actually requires.) · held-out generators hash-locked, **and the authoring session's tool-call log, committed as `experiments/heldout_session_manifest.json`, shows no read of `src/arc_plasticity/environments/dev/**`** — a referee inspects this; a script only checks the log exists and contains no such path · **leak check: a referee inspects a sampled observation dump against `docs/LEAK_CHECKLIST.md`** — semantic judgement, not scriptable |
| **G5** Baseline freeze | **B0–B3 and B5–B7 on every tier-1 family; B8–B13 only on the families used by the mechanism that mandates them** (running ROME/MEMIT against five grid-game generators before M4 exists is weeks of work with no purpose) | Each baseline's variance across its declared seeds is within the tolerance recorded in its config · budgets recorded in every manifest · baseline code tagged and frozen in git before any mechanism run · **`docs/FAILURE_TAXONOMY.md` exists and a referee confirms it classifies the observed failures rather than merely listing runs** |
| **G6** M1 campaign | Mechanism card, inhibition without context conditioning, context conditioning without inhibition, combined, ablations | **Gate closes on:** pre-registration committed and hashed **before** the first treatment run · every mandated baseline run · a referee verdict citing artifact hashes. **Mechanism passes to G10 additionally on:** the M1 pass rule as defined in §4 (which names B9, B10 and B13) · improvement in ≥3 families · **held-out families satisfy the same pass rule** (this is what "survives" means; the threshold lives in the pre-registration) · collateral forgetting within tolerance · **the ablation removes ≥70% of the gain** (the single threshold; §10's "most of the gain" refers here) · reproduces across ≥3 seeds |
| **G7** M2 campaign | Eligibility, instructive-event signal, fast/slow weight isolation, gate-policy ablation | As G6, mandated baselines **B6 and the random-gate control at matched write count** |
| **G8** M3 campaign | Selection operator and recombination operator, separately and combined | As G6, mandated baselines **B8 (EVB)** and B5 at matched simulation count; the recombination ablation must remove the compositional advantage specifically |
| **G9** M4 campaign *(conditional: runs only if M1's verdict is GO; otherwise `gate_status: "skipped"`)* | PE-gated scoped unlock and relock | As G6, mandated baseline **B11 (ROME/MEMIT)**; the contribution tested is the trigger, not the edit |
| **G9b** M5 unit test *(conditional: runs only if G5–G8 recorded a relational-binding failure)* | Compact architectural unit test | As G6, against a parameter-matched conventional architecture. **If the trigger never fires, `gate_status: "skipped"` and no verdict is required** |
| **G10** Integration | Factorial over surviving mechanisms only; transparent rule-based controller first | Only independently-passing mechanisms enter · full 2^k factorial run · interaction effects reported with confidence intervals · combined must beat the strongest single component or the combination is rejected |
| **G11** Wireless transfer | Black-box wireless environment; same plasticity core | **`configs/transfer_invariants.yaml` names the exact `invariant_paths:` (the plasticity core) and `adapter_paths:` (what may change); the automated diff check asserts zero changes under `invariant_paths`** — without that file the check has nothing to compare against · improvement over **a domain-specific probing baseline named in the pre-registration** in hidden-cause identification, probe efficiency and post-regime-change adaptation · retention of prior mechanisms within tolerance |
| **G12** Manuscript | Claim–evidence matrix, novelty audit, negative-results archive | Script-checkable: **every citation either resolves or is listed in `docs/UNRESOLVED_CITATIONS.md` with a reason** (seed that file now with the three placeholder DOIs in `EVIDENCE_NEURO.md` — `10.1016/j.tins.2025.07.xxx`, `10.1016/j.neuron.2024.11.xxx`, `10.1016/j.neubiorev.2025.106xxx` — and with every open-square entry awaiting verification) · no claim uses "first", "unprecedented" or "never attempted" without a documented search. **Referee-checkable: every row of `CLAIM_EVIDENCE_MATRIX.md` maps to an experiment, config, figure, statistical test and limitation, and the referee confirms the matrix is complete against the manuscript** — a script cannot enumerate claims from prose |

**Gate discipline.** No gate may be entered until its predecessor's predicate evaluates true.
No pre-registration may be edited after the first treatment result exists for that gate; a
`PreToolUse` hook enforces this at the filesystem level. Negative results are outputs, and a
KILL verdict advances the project.

---

## 10. Advancement and termination rules

Pre-registration defaults, revisable **once** before experiments begin and never after seeing
treatment results.

**Advance** when all applicable conditions hold: ≥15% relative improvement in the primary
targeted metric; paired bootstrap CI excluding zero; improvement in ≥3 environment families;
improvement surviving held-out generator families; unrelated-task regression ≤5%; total
internal compute ≤2× the matched baseline unless the efficiency gain is unusually large;
mechanism-specific ablation removes most of the gain; reproduction across ≥3 independent seeds.

**Kill or suspend** when any holds: a simpler baseline matches it; the effect exists only on
development environments; the effect disappears under matched computation; the biological
detail can be removed without changing results; performance depends on one prompt; the
mechanism creates unacceptable forgetting or instability; **a frozen model at the project's
maximum context matches it on the context-clear variant ▲**; or two principled revisions fail.

Revision limit: **two** per mechanism, pre-registered. Do not rescue a failing hypothesis by
adding components.

---

## 11. Threats to validity

v1.0's nine threats are retained: stronger-model confound, compute confound, public-task
overfitting, perception confound, memory-capacity confound, prompt confound,
biological-metaphor confound, multiple-testing bias, hidden-distribution mismatch. Their
controls are unchanged.

**Three threats are added, and they are the ones most likely to sink the project.**

**T10 — In-context learning substitutes for plasticity.** *The most serious threat.* Frontier
reasoning models close most of the interactive-learning gap with no weight updates at all
(Csaba et al. 2026). If an experiment can be passed by a frozen model with a long enough
context, it does not test the thesis.
*Control:* gate predicate `G-CTX` (§9, G4) — every tier-1 family must ship a context-clear
variant on which a frozen-model control **at the project's maximum context** does not exceed the
persistent-state-ablated agent by more than a pre-registered δ. Families failing this are
rejected before any mechanism touches them.

*Honest counterweight, so the concession is not overstated:* in the Csaba et al. study the
frontier models solved **11–65% of level instances against 75% for humans** — they narrow the
gap markedly, they do not close it. The threat is that they narrow it enough to swamp a
mechanism effect, not that the problem is solved.

**T11 — Priors, not plasticity, explain human efficiency.** EMPA matches human efficiency on
79/90 games with Bayesian theory induction and no plasticity innovation (Tsividis et al. 2026);
Dubey et al. (2018) showed prior ablation costs humans ~10×, a large but insufficient factor.
*Control:* concede this in the introduction rather than defending against it, and confine every
claim to cross-episode retention, interference and composition. Report EMPA-style theory
induction as part of the reference architecture, not as a competitor.

**T12 — The mechanism is a renamed existing method.** M1 against Vogels–Sprekeler 2011, M2
against e-prop and RFLO, M3 against EVB, M4 against ROME and MEMIT, context inference against
BOCPD and Hummos 2023.
*Control:* each of those is a mandatory baseline in §7, implemented by the project itself, not
cited. A mechanism that does not beat its nearest prior method has been shown to be that
method.

---

## 12. Cross-domain validation: active wireless system identification

Unchanged in purpose, strengthened in rationale. The offline, compute-bounded, active-probing
regime is exactly wireless system identification: hidden causes (blockage, beam misalignment,
narrowband interference, mobility, oscillator drift, calibration error, congestion) that must
be discriminated by choosing informative and safe probes (test a beam, request a pilot, sense
another frequency, modify power, obtain a neighbouring-cell measurement).

The transfer test is mechanical, not rhetorical: the diff of the plasticity module between the
ARC build and the wireless build must touch only input adapters, output adapters and
domain-specific primitive definitions. `G11` checks this automatically. A result is not
reported as general unless that diff check passes.

Measured: hidden-cause identification accuracy, probe count, outage or failure risk, adaptation
after a regime change, retention of earlier mechanisms, calibration, compute.

---

## 13. Novelty audit protocol

Before implementing each mechanism and again before any manuscript claim, search at minimum:
ARC-AGI agent architectures; active causal discovery; Bayesian experimental design; model-based
RL; program synthesis; test-time training; fast-weight networks; continual learning; agent
memory; memory suppression and selective forgetting; machine unlearning; activation steering
and representation engineering; model editing; reconsolidation-inspired AI; neural replay;
thalamic gating models; dendritic neural networks; metaplasticity.

For each claimed contribution record: the nearest prior mechanism; exact shared components;
exact difference; whether the difference is structural or terminological; whether a simpler
known method reproduces the effect; and which experiment supports the distinction.

The evidence base already names the nearest prior work for every mechanism (§4). The audit's
job is to keep that current, not to rediscover it.

Never claim novelty because a mechanism has a neuroscience-inspired name, combines known
modules, has not been applied to ARC under the same label, or because a quick search found no
exact phrase.

---

## 14. Deliverables

1. Reproducible mechanism-laboratory repository, MIT-0.
2. Procedural interactive environment suite with oracles, splits and context-clear variants.
3. RHAE implementation validated against a published score.
4. Human-baseline dataset derived from the 342 public replays.
5. Reference architecture (verified executable world model) at ≥60% RHAE on public games.
6. Baseline benchmark report across the full ladder.
7. One mechanism card per tested architecture.
8. Raw transition, hypothesis and memory-operation logs for every run.
9. Formal `GO` / `REVISE_ONCE` / `KILL` / `SUSPEND_FOR_DEPENDENCY` verdict for every tested
   mechanism, referee-issued. These four strings are the enum; nothing abbreviates them.
10. Negative-results archive.
11. Surviving integrated architecture, if justified.
12. Wireless transfer experiment with an automated core-invariance check.
13. Novelty and claim–evidence matrices.
14. Research manuscript centred on the mechanism.

---

## 15. Final decision rule

The project is not judged by whether every radical idea succeeds. A successful programme
quickly distinguishes mechanisms that sound biologically interesting but add no computational
value; mechanisms equivalent to simpler existing methods; domain-specific improvements; and
genuinely reusable learning primitives.

Priority order, revised:

```
M1 context-conditioned inhibitory suppression
  → M2 gated one-shot write
    → M3 selective and compositional replay
      → M4 retrieval-gated scoped unlock   (conditional on an M1 GO)
        → M5 dendritic conjunctive microcircuits
             (reserve: runs only on a measured relational-binding failure;
              if never triggered it needs no verdict and the programme is
              still complete)
```

A mechanism becomes a serious candidate for a field-defining contribution only when it improves
**cross-episode** hidden-mechanism learning under matched budgets, in conditions where
in-context inference provably cannot substitute for it, and transfers beyond ARC with the same
computational core.

Only evidence — not biological attractiveness — determines what survives.
