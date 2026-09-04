# Evidence Base, Part B: Neuroscience Literature Scan

**Status:** verified external evidence, compiled 2026-09-04 for the ARC-AGI-3 Plasticity Lab.
**Authority:** this document is the project's ground truth for neuroscience claims. The
autonomous agent MUST cite from here rather than from model memory. Any claim not in this
document, and not added to it by a fresh literature search that records DOIs, is speculation
and must be labelled as such in NOVELTY_AUDIT.md.

**How to read the marks:** entries marked with a check were retrieved and read during
compilation. Entries marked with an open square are canonical references cited without
re-fetching; their DOIs and page numbers must be verified before any manuscript submission.
Preprint versus peer-reviewed status is flagged on every entry and must be preserved in
every downstream citation.

> ## ⚠️ NUMBERING WARNING — READ BEFORE ACTING ON ANYTHING IN THIS FILE
> This scan was written against the **v1.0** mechanism numbering. `PROPOSAL_v2.md` §4
> renumbered the portfolio on the strength of this very scan. Every `M<n>` and every
> primitive name below is **v1.0**. The mapping is:
>
> | v1.0 | v1.0 name | v2.0 | v2.0 status |
> |---|---|---|---|
> | M1 | Inhibitory memory **+ localized reconsolidation** | **split** | inhibition → **v2.0 M1**; reconsolidation → **v2.0 M4** |
> | M2 | Uncertainty-triggered compositional **preplay** | **v2.0 M3** | narrowed; the word *preplay* is deleted |
> | M3 | Event-triggered fast causal binding | **v2.0 M2** | reframed as gated one-shot write |
> | M4 | Rapid latent-context inference and gating | — | **demoted to infrastructure**, not a contribution |
> | M5 | Dendritic conjunctive microcircuits | **v2.0 M5** | reserve, unchanged |
> | M6 | Slow plasticity governor (astrocytic) | — | **dropped** |
>
> So where this document says *"the citation your M1 needs"* about Doyère 2007, it means
> **v2.0 M4**. Where it says *"your proposal's PREPLAY primitive"*, v2.0 has no PREPLAY
> primitive — read it as the recombination operator of **v2.0 M3**. When in doubt,
> `PROPOSAL_v2.md` §4 governs and this file supplies only the evidence.

---

# Plasticity-Control-Plane Literature Scan

**Scope note on verification:** Everything marked ✅ I retrieved and read this session (title, authors, venue, DOI, and the actual measurement). Items marked ◻︎ are canonical references I am citing from knowledge without re-fetching — the claims are standard but **verify the DOI/page numbers before submission**. Peer-reviewed vs. preprint is flagged on every entry.

---

## 1. HIPPOCAMPAL REPLAY AND PREPLAY AS COMPUTATION

### (a) Strongest recent empirical findings

**Replay is selective, and selection happens at encoding, not at consolidation.**
- ✅ **Yang, Sun, Huszár, Hainmueller, Kiselev & Buzsáki (2024), *Science* 386(6690):1478–1483, DOI 10.1126/science.adk8261** — peer-reviewed. Dual-sided silicon probes, mouse CA1, figure-8 maze. *Measured:* which trial identity is decodable from SWR spike content. Awake SWR content decoded the *present* trial most reliably; the distribution of trial identities replayed during subsequent sleep correlated with the awake-SWR distribution at **R = 0.86**, and awake-SWR replay was the strongest regression predictor of sleep replay content — stronger than novelty or ripple rate at encoding. This is the cleanest existing evidence that ripples act as a **tagging/selection operator**, not a uniform rehearsal buffer.

**Ripples track uncertainty prospectively in humans.**
- ✅ **Frank, Moratti, Hellerstedt, Sarnthein, Li, Horn, Imbach, Stieglitz, Gil-Nagel, Toledano, Friston & Strange (2026), *Nature Neuroscience*, DOI 10.1038/s41593-026-02345-6** — peer-reviewed. Human iEEG, 17 patients, hippocampus + occipital/fusiform, visuomotor selection task with block-wise entropy manipulation (1.7–1.9 bits). *Measured:* 2,728 ripples. **Pre-stimulus** ripple rate and duration increased with entropy, peaking −800 to −400 ms before stimulus onset; duration scaled *positively* with entropy pre-stimulus and *negatively* post-stimulus (interaction p = 0.0416). Pre-stimulus ripples suppressed occipital gamma and accelerated fusiform responses to surprising stimuli. This is your single best citation for "ripples are gated by uncertainty," and it is human and intracranial.

**Ripples carry compositional recombination in humans.**
- ✅ **He, Wang, Zhang, Xiao, Hu, Schwartenbeck, Bakermans, Behrens & Liu (2026), *Nature Neuroscience*, DOI 10.1038/s41593-026-02291-3** — peer-reviewed. Human iEEG, 28 epilepsy patients, simultaneous hippocampal + cortical, two LEGO-like relational inference tasks. *Measured:* mPFC representational content time-locked to hippocampal ripples. Ripple-locked replay reorganized familiar "building blocks" into candidate novel sequences; mPFC shifted toward inferred relational configurations around ripples, and ripple-locked replay strength predicted inferential efficiency. **This is the paper your proposal's PREPLAY primitive should be built on.** It is compositional recombination, in humans, measured directly, published.
- ◻︎ **Liu, Dolan, Kurth-Nelson & Behrens (2019), *Cell* 178(3):640–652, DOI 10.1016/j.cell.2019.06.012** — peer-reviewed. MEG; human replay during rest reorders experienced sequences into inferred structural order (factorized structure + sensory code). Canonical precursor.
- ◻︎ **Liu, Mattar, Behrens, Daw & Dolan (2021), *Science* 372:eabf1357, DOI 10.1126/science.abf1357** — peer-reviewed. MEG; replay magnitude predicts **non-local** value updating (learning about states not currently visited).

**Ripple priority tracks the normative value of a backup.**
- ✅ **"Human hippocampal ripples prioritise model-based learning" (2025), bioRxiv 2025.07.31.667862** — **PREPRINT, not peer-reviewed.** Human iEEG, 34 patients, 157 hippocampal contacts, three-armed bandit with local and non-local value updates. *Measured:* ripple rate was highest on rare-arm trials where non-local update priority was greatest; long-duration ripples were most sensitive to priority. Direct empirical support for a Mattar–Daw-style prioritization signal in human hippocampus. Flag as preprint.

**What triggers replay — dopamine is causal in rodents.**
- ✅ **"Spatial localization of hippocampal replay requires dopamine signaling," *eLife* (reviewed preprint / eLife assessment), eLife 99678** — *reviewed preprint status; check final version of record.* Dopamine signaling is required for replay to be spatially localized to relevant content.

### Contested / negative results — you will be hit with these

- ✅ **Deceuninck & Kloosterman (2024), *eLife* 13:e84004, DOI 10.7554/eLife.84004** — peer-reviewed. Closed-loop awake-SWR disruption in rats across three spatial memory tasks (NMTS, MTS, SEQ). *Measured:* accuracy, correct visits, learning speed. **No significant difference** between disruption and control on any task. Editors called the evidence "solid." This directly contradicts the standard reading of ◻︎ Jadhav, Kemere, German & Frank (2012), *Science* 336:1454–1458, DOI 10.1126/science.1217230.
- ✅ **Widloski & Foster (2025), *Nature Communications*, DOI 10.1038/s41467-025-65181-5** — peer-reviewed. Rats, up to 295 simultaneously recorded CA1 place cells, ripple-independent replay detector. **20–24% of detected replays had neither ripples nor population bursts** yet showed long-duration, smoothly varying spatial content. Ripples and replay are **dissociable**. The authors' own reading: ripples *tag* a subset of replays rather than generate them — which is actually good for your control-plane framing, but it means you cannot use "ripple" and "replay" interchangeably anywhere in the proposal.
- ✅ **Thompson, Rollik, … Stephenson-Jones (2026), *Nature Neuroscience*, DOI 10.1038/s41593-026-02362-5** — peer-reviewed. Mice, dorsal striatum Neuropixels, five-port sequential procedural task, PP-Seq sequence detection, bilateral caspase hippocampal lesions. *Measured:* striatal awake sequences replayed in NREM and REM; replay and learning **fully intact after hippocampal ablation**. Replay is a general circuit motif, not a hippocampal privilege. Useful for you: it makes replay a *plausible generic primitive*, but it removes "the hippocampus does it" as an argument.
- ✅ **Takigawa, Huelin Gorriz, Tirole & Bendor (2024), *eLife* 13:e85635, DOI 10.7554/eLife.85635** — peer-reviewed. **Methodological.** No ground truth exists for replay; nominal α = 0.05 corresponds to actual false-positive rates of **2–18%** depending on shuffle procedure; using all spikes in rank-order analyses inflates FPR to ~17%. Any reviewer who knows this paper will ask whether the replay literature you cite used pre- or post-decoding shuffles. Pre-empt it.
- **Preplay specifically is the weakest sub-claim in this whole area.** ◻︎ Dragoi & Tonegawa (2011), *Nature* 469:397–401, DOI 10.1038/nature09633 reported preplay of future place-cell sequences. ◻︎ Silva, Feng & Foster (2015), *Nature Neuroscience* 18:1772–1779, DOI 10.1038/nn.4151 ("Trajectory events across hippocampal place cells require previous experience") found the opposite. ◻︎ Grosmark & Buzsáki (2016), *Science* 351:1440–1443, DOI 10.1126/science.aad1935 split the difference — preconfigured "rigid" sequences plus learned ones. ◻︎ Foster's commentary "Does the hippocampus preplay memories?" *Nature Neuroscience* (2015/16), DOI 10.1038/nn.4180. **Recommendation: do not build PREPLAY on rodent preplay.** Build it on He et al. 2026 human compositional replay, which is a different and much better-supported claim.

### (b) Minimal computational abstraction licensed

A **priority-gated, content-selective backup operator**: at time *t*, given a set of candidate transitions/states, compute a scalar priority *ρ(s)* (driven by uncertainty, non-locality of the value update, and recency-of-tagging), and apply a bounded number of off-policy updates sampled ∝ *ρ*. Plus a weaker, separate **recombination operator**: sample sequences from a factorized world model that were never experienced as sequences.

Note the abstraction the data actually license is *two* operators, not one. Selection/tagging (Yang 2024) and recombination (He 2026) are dissociable, and Widloski & Foster show the physiological marker (ripple) tracks the first more tightly than the second.

### (c) Closest existing AI method

- **Prioritized Experience Replay** (Schaul, Quan, Antonoglou & Silver, ICLR 2016, arXiv:1511.05952) — TD-error-based priority. Already does the selection operator, badly.
- **Dyna** (Sutton, 1991) and **prioritized sweeping** (Moore & Atkeson, 1993) — the actual ancestor.
- ◻︎ **Mattar & Daw (2018), *Nature Neuroscience* 21:1609–1617, DOI 10.1038/s41593-018-0232-z** — peer-reviewed. Expected Value of Backup (gain × need). This is *already* the normative theory your control plane would be re-deriving, and it already fits rodent and human replay data. **A hostile reviewer will say your RETRIEVE/PREPLAY primitives are EVB with new names.** You need a specific answer to that.
- For recombination: model-based rollout in MuZero/Dreamer, and hindsight/counterfactual replay (HER).

**Gap vs. AI:** modest for selection, real for recombination. Nothing in mainstream RL does compositional recombination of *structural* building blocks the way He et al. describe — that's closer to program synthesis than to replay.

---

## 2. BEHAVIORAL-TIMESCALE SYNAPTIC PLASTICITY (BTSP)

### (a) Strongest recent empirical findings

**The canonical result.**
- ◻︎ **Bittner, Milstein, Grienberger, Romani & Magee (2017), *Science* 357(6355):1033–1036, DOI 10.1126/science.aan3846** — peer-reviewed. Single dendritic plateau potential in CA1 pyramidal neuron creates a place field in one trial, potentiating synapses active within a seconds-long window around the plateau.
- ◻︎ **Bittner, Grienberger, Vaidya, Milstein, Macklin, Suh, Tonegawa & Magee (2015), *Nature Neuroscience* 18:1133–1142, DOI 10.1038/nn.4062** — peer-reviewed. Plateau potentials as conjunctive CA3/EC input signal.

**Current authoritative synthesis.**
- ✅ **Magee (2026), "Behavioral timescale synaptic plasticity: properties, elements and functions," *Nature Neuroscience*, DOI 10.1038/s41593-026-02214-2** — peer-reviewed review. Affects weights "over many seconds"; induced by **single dendritic plateau potentials, not many action potentials**; produces a new place cell in one trial; instructive input plausibly from a higher-order region (entorhinal cortex). Notably, **this review does not present evidence for BTSP outside CA1.**
- ✅ **Madar, Milstein, O'Dell, Jain, Clopath & Sheffield (2025), *Journal of Neuroscience* 45(46):e1332252025, DOI 10.1523/JNEUROSCI.1332-25.2025** — peer-reviewed review. States the two-factor form explicitly: presynaptic spikes trigger a **local** eligibility signal with a long decay constant; the plateau triggers a **multidendritic/global** instructive signal with a long but *shorter* constant; asymmetry between the two constants sets the directional bias. Effective window **~±5 s** around the plateau. Molecular substrate: dendritic Ca²⁺ extended via ER release, CaMKII autophosphorylation. This review also **does not report BTSP outside CA1.**
- ✅ **Sheffield lab: Madar, Jiang, Dong & Sheffield (2025), *Nature Neuroscience*, DOI 10.1038/s41593-025-01894-6** — peer-reviewed. Two-photon Ca²⁺ imaging, mouse CA1 and CA3, familiar vs. novel environments. *Measured:* place-field shifting dynamics fit against competing plasticity rules. **BTSP, not STDP, best explains PF shifting.** BTSP induction events are rare, increase in novelty, and their probability decays after PF onset while continuing to drive population-level representational drift. BTSP is **less frequent in CA3 than CA1**.
- ◻︎ **CaMKII requirement:** *Science Advances*, DOI 10.1126/sciadv.adi3088 — peer-reviewed.

**BTSP outside CA1 — this is the answer to your specific question.**
- ✅ **"Plateau potentials are instructive signals for behavioral timescale synaptic plasticity in the neocortex" (2025), bioRxiv 10.1101/2025.11.07.687250; also indexed PMID 41279115** — **PREPRINT.** Mice, **primary visual cortex layer 5** pyramidal neurons; whole-cell patch in awake head-fixed animals viewing naturalistic movies, plus slice ephys. *Measured:* plateaus in **45/83 L5 neurons (54%)**, mean duration 48 ± 1.5 ms at 0.16 ± 0.03 Hz; **only plateaus >200 ms drove plasticity**; single long plateaus produced persistent ΔVs = 5.68 ± 0.46 mV (spontaneous) / 4.09 ± 0.46 mV (injected); seconds-long timing rule with potentiation over **−2 s to +0.5 s**. **Plateaus confined to L5 — absent in L2/3 and L4.**

This is the best evidence you have for BTSP in cortex, and it is (i) a preprint, (ii) layer-restricted, and (iii) has a **markedly narrower and more asymmetric window (−2 s to +0.5 s) than CA1's ±5 s**. Cite it, flag the preprint status, and do not over-generalize "BTSP is a cortical rule." **There is no human BTSP evidence.** None. Do not imply otherwise.

### (b) Minimal computational abstraction licensed

A **two-factor, gated, one-shot credit assignment rule**: maintain a slowly decaying per-synapse eligibility trace *e_ij(t)* from presynaptic activity alone (τ ≈ 1–3 s); on arrival of a **sparse, cell-wide, top-down binary gate** *G(t)* (the plateau), apply Δw_ij ∝ f(e_ij, w_ij) — with the crucial detail from Wu & Maass that the update is **weight-dependent and does not require postsynaptic firing**.

The three properties that are genuinely non-standard: (1) the gate is *not* a scalar global reward but a **per-neuron, dendritically computed, top-down instructive event**; (2) the rule is **postsynaptically-independent** — it is not Hebbian; (3) it is **one-shot and saturating**, not incremental.

### (c) Closest existing AI method — and is BTSP actually distinct?

- ◻︎ **e-prop:** Bellec, Scherr, Subramoney, Hajek, Salaj, Legenstein & Maass (2020), *Nature Communications* 11:3625, DOI 10.1038/s41467-020-17236-y — peer-reviewed. Eligibility traces × top-down learning signal.
- ◻︎ **RFLO:** Murray (2019), *eLife* 8:e43299, DOI 10.7554/eLife.43299 — peer-reviewed. Local online RNN learning with random feedback.
- ◻︎ **Three-factor rules:** Frémaux & Gerstner (2016), *Front. Neural Circuits* 9:85; Gerstner, Lehmann, Liakoni, Corneil & Brea (2018), *Front. Neural Circuits* 12:53.
- ✅ **Three-factor learning in SNNs: a 2025 survey,** *Patterns*, DOI 10.1016/j.patter.2025.101401 (verify exact DOI) — peer-reviewed overview of the ML landscape.

**Blunt answer to your question: BTSP is ~70% already-had by ML, ~30% genuinely new.**

What ML already has: eligibility traces with seconds-scale time constants, multiplied by an instructive third factor. That is e-prop, that is RFLO, that is every actor-critic with traces. If your proposal frames BTSP as "eligibility trace + instructive signal," **a reviewer will correctly say this is a 2020 result.**

What ML does *not* have, and where your proposal should stand:
1. **The gate is a learned, per-neuron, sparse, structured decision** — a plateau is an inference about "this input is worth binding now," computed from conjunctive top-down input, not a broadcast reward. This is the FAST_BIND primitive and it is the defensible core.
2. **Postsynaptic-independence + weight-dependence + binarity.** ✅ **Wu & Maass (2025), *Nature Communications* 16:342, DOI 10.1038/s41467-024-55563-6** — peer-reviewed. Stochastic BTSP on **binary** weights, flip probability 0.5 within a 10 s window, depends on presynaptic activity and prior weight only. Achieves one-shot storage with 0.5% activation sparsity, tolerates 30% pattern overlap, robust to 1/3 masked bits; theory projects recall for up to **800,000 items** with 2/3 masking; **instant** recall vs. ~100 iterations for Hopfield; and it reproduces the human **repulsion effect** which the authors state no Hopfield variant or other rule has reproduced. Their explicit claim: BTSP is "not just a variant of STDP on a longer time scale."
3. **The rate of gating events is itself modulated by novelty** (Madar 2025) — the gate is under control-plane regulation. That is exactly your thesis, and it is the strongest neuroscience-to-computation bridge in your whole proposal.

**Recommendation: reframe BTSP in the proposal from "eligibility traces" (already had) to "learned sparse write-gating over a content-addressable binary store" (not had).**

---

## 3. INHIBITORY PLASTICITY, SUPPRESSION, RETRIEVAL-INDUCED FORGETTING

### (a) Strongest recent empirical findings

**Inhibitory plasticity as an active *selection* operator on replay — the best paper for your SUPPRESS primitive.**
- ✅ **Liao, Terada, Raikov, Hadjiabadi, Szoboszlay, Soltesz & Losonczy (2024), *Nature Neuroscience*, DOI 10.1038/s41593-024-01745-w** — peer-reviewed. Awake behaving mice, optogenetics + three-level modeling (LIF, biophysically detailed, abstract binary). *Measured:* salient stimuli were either **recruited into or actively suppressed from** SWRs. A Hebbian STDP rule *at inhibitory synapses* parsimoniously explains the selectivity. Critical test: artificially implanted **non-generalizable** representations **accumulated inhibition during ripples**, as the model predicted. This is inhibition performing a computation — deciding what does *not* get consolidated — not gain control.

**Inhibitory plasticity is heterogeneous and cell-type-structured.**
- ✅ **Favila, Capece Marsico, Pacheco, Kenet, Escribano, Bitterman, Gründemann, Lüthi & Krabbe (2025), *Nature Communications* 16:9926, DOI 10.1038/s41467-025-66122-y** — peer-reviewed. Freely moving mice, GRIN-lens miniscope Ca²⁺ imaging of BLA interneurons (SST, PV, VIP, CCK) across habituation → conditioning → extinction; 58 ± 6 interneurons/animal over 4 days. *Measured:* 76 ± 2% responded to US, 58 ± 3% to CS+; distinct plasticity clusters ("Activated down" 29%, "Stable activated" 24% for CS+); **VIP 48% stable US activation vs. SST 16%; VIP 49% vs. SST 19% stable CS+**; within-day decoding 94 ± 3%, across-day ~60%. A "Stable activated" pattern emerged **only for CS+**. Interneuron plasticity is associatively specific, cell-type-differentiated, and encodes internal fear *state* independent of external cue.

**Peptidergic control of the lability/stability switch — bridges areas 3 and 4.**
- ✅ **Wu, Gu, Kong, Yang et al. (2026), *Nature Neuroscience*, DOI 10.1038/s41593-026-02235-x** — peer-reviewed. Mice, ventral CA1, fiber photometry with NPY1.0 sensor, GCaMP6m in NPY⁺ interneurons, ephys, scRNA-seq. *Measured:* NPY⁺ GABAergic interneurons use **fast GABAergic inhibition to support acquisition and slow NPY-mediated inhibition to support extinction**; NPY acts on **two non-overlapping populations (NPY1R⁺ and NPY2R⁺)** gating early-fast and late-slow extinction stages; NPY is necessary and sufficient to control the **rate and degree** of extinction. Two distinct inhibitory timescales with distinct receptor-defined targets — this is close to a literal implementation of a graded SUPPRESS operator.

**Engram competition and targeted downstream suppression.**
- ✅ *PNAS* (2025), DOI 10.1073/pnas.2410101122, "Reactivation of memory-associated neurons induces downstream suppression of competing neuronal populations" — peer-reviewed (I could not fetch the full text; 403. **Verify the measurement details before citing.**)
- ✅ **"The cost of remembering: engram competition as a flexible mechanism of forgetting," *Trends in Neurosciences* (2025), DOI 10.1016/j.tins.2025.07.xxx** — peer-reviewed review; verify DOI.
- ✅ **"Inhibitory tone in the dentate gyrus dynamically prioritizes memory flexibility or stability by tuning a sensitivity-consistency continuum," *PLOS Biology* (2025), DOI 10.1371/journal.pbio.3003956** — peer-reviewed. Inhibitory tone as an explicit **control parameter** on a flexibility/stability axis. Good framing citation.

**Human retrieval suppression.**
- ◻︎ **Anderson & Green (2001), *Nature* 410:366–369, DOI 10.1038/35066572** — canonical think/no-think.
- ✅ **Wimber, Alink, Charest, Kriegeskorte & Anderson (2015), *Nature Neuroscience* 18:582–589, DOI 10.1038/nn.3973** — peer-reviewed. "Retrieval induces adaptive forgetting of competing memories via cortical pattern suppression." fMRI + MVPA. *Measured:* the **cortical pattern of the competing memory** is specifically suppressed across repeated selective retrievals, and the degree of suppression predicts later forgetting of that competitor. **This is the single best evidence that suppression is targeted at a specific representation rather than being global gain reduction.**
- ✅ **Schmitz & Anderson (2017), *Nature Communications* 8:1311, DOI 10.1038/s41467-017-00956-z** — peer-reviewed. n = 24 fMRI; ¹H-MRS J-resolved with ProFit; hippocampus n = 18, DLPFC n = 23, visual n = 20. *Measured:* resting **hippocampal** GABA/Cr predicted suppression-induced forgetting and predicted the strength of **negative** DLPFC→hippocampus coupling during suppression. Anatomically specific (not DLPFC or visual GABA).
- ✅ **Hulbert, Henson & Anderson (2016), *Nature Communications* 7:11003, DOI 10.1038/ncomms11003** — peer-reviewed. "Inducing amnesia through systemic suppression" — retrieval stopping produces a **temporal amnesic shadow** for unrelated events, i.e. suppression has a *systemic* cost. Important nuance: the operator is not free.
- ✅ **Barron, Vogels, Behrens & Ramaswami (2017), *PNAS* 114(26):6666–6674, DOI 10.1073/pnas.1701812114** — peer-reviewed Perspective. "Inhibitory engrams in perception and memory." The theoretical statement of a **matched, memory-specific inhibitory trace that silences rather than erases**.

### Contested

Suppression-induced forgetting has a real replication history. ◻︎ Bulevich, Roediger, Balota & Butler (2006), *Memory & Cognition* 34:1569–1577 failed to find it. A **multiverse analysis of early TNT replication attempts** (*Memory*, 2020, DOI 10.1080/09658211.2020.1797095) is standard hostile-reviewer ammunition — I could not fetch it (403), so **read it yourself before citing**. Against that: ✅ a pre-registered replication (*Memory*, 2023, DOI 10.1080/09658211.2023.2208791) and ✅ **Niczyporuk (2025), *Psychonomic Bulletin & Review*, DOI 10.3758/s13423-025-02763-w** — peer-reviewed, which concludes from two meta-analyses that SIF is a **small-to-moderate but reliably replicable** effect in healthy participants, **and is not significant in clinical/subclinical samples**. Also ✅ **Wessel et al. (2024), *Topics in Cognitive Science*, DOI 10.1111/tops.12684** for the critical view. Net: the *phenomenon* survives; the *effect size* is small; don't oversell.

### (b) Minimal computational abstraction licensed

A **context-specific inhibitory trace** is best formalized as a **learned, additively-composed negative-key memory in the same representational space as the excitatory trace**:

Given a stored pattern *p* and a context *c*, learn a second trace *I(c, ·)* such that the effective retrieval score becomes `score(q) = ⟨q, W_E⟩ − g(c)·⟨q, W_I⟩`, where:
- *W_I* is learned by a **Hebbian rule at inhibitory synapses driven by co-activation during competition** (Liao 2024; Vogels 2011),
- *g(c)* is a **context gate** — so the same excitatory trace is retrievable in one context and silent in another,
- suppression is **subtractive and matched in the representation**, not a multiplicative gain (Wimber 2015 shows the *specific competitor pattern* is what goes down),
- and the trace is **reversible** — the memory is silent, not erased (Barron 2017).

The Favila and Wu results add that biology uses **at least two inhibitory timescales with distinct targets**, so the honest minimal abstraction has a fast mask and a slow mask.

### (c) Closest existing AI method

- ◻︎ **Vogels, Sprekeler, Zenke, Clopath & Gerstner (2011), *Science* 334(6062):1569–1573, DOI 10.1126/science.1211095** — peer-reviewed. Canonical inhibitory plasticity rule; E/I balance; **memories are silent until inhibition is unmasked**. This is already the computational form you want, and it is 15 years old.
- **Negative/contrastive keys** in retrieval-augmented systems; hard-negative mining.
- **Machine unlearning** (gradient ascent on a forget set) and **activation steering / representation engineering** — closest live ML analogues to "targeted suppression of a specific representation."
- **Weight/attention masking, LoRA-based feature ablation, SAE feature clamping.**

**Gap vs. AI: this is the area where ML is weakest relative to biology.** ML has no principled, learned, *context-conditioned, reversible* suppression of a specific memory. Machine unlearning is destructive and famously leaky; activation steering is hand-specified, not learned; there is no "inhibitory engram" that is itself learned by the same competitive dynamics that created the excitatory one. **This is your best gap.**

---

## 4. RECONSOLIDATION AND SELECTIVE MEMORY EDITING

This is your most dangerous area. Handle it explicitly or a reviewer will kill it.

### (a) Strongest empirical findings, and the state of the controversy

**The phenomenon in rodents is solid.**
- ◻︎ **Nader, Schafe & LeDoux (2000), *Nature* 406:722–726, DOI 10.1038/35021052** — peer-reviewed. Intra-amygdala anisomycin after retrieval abolishes a consolidated fear memory. Canonical.

**Localized editing — YES, there is direct evidence, and this is the citation your M1 needs.**
- ✅ **Doyère, Debiec, Monfils, Schafe & LeDoux (2007), *Nature Neuroscience* 10(4):414–416, DOI 10.1038/nn1871** — peer-reviewed. Rats; electrophysiological recording of two independent auditory input pathways to lateral amygdala, each conditioned to a different CS. *Measured:* retrieval of one CS produced synaptic potentiation **selective to the reactivated pathway**, and reconsolidation blockade reduced potentiation **only at those synapses**. The non-reactivated memory's synapses were untouched. **This is input-specific, i.e. localized, reconsolidation, measured at the synapse.**
- ◻︎ **Debiec, Doyère, Nader & LeDoux (2006), *PNAS* 103:3428–3433** — peer-reviewed. Trace-specific reconsolidation in second-order conditioning.
- ◻︎ **"Sensory-Specific Associations Stored in the Lateral Amygdala Allow for Selective Alteration of Fear Memories," *J. Neuroscience* 31(26):9538 (2011)** — peer-reviewed. Selective alteration of one sensory component of a compound fear memory.
- ✅ **"Reconstructing a new hippocampal engram for systems reconsolidation and remote memory updating," *Neuron* (2024/2025), DOI 10.1016/j.neuron.2024.11.xxx (PMID 39689709)** — peer-reviewed. Remote memory updating via reconstruction of a *new* hippocampal engram rather than modification of the old one. **Note: this is a mild argument against pure in-place editing** — worth reading closely because it cuts both ways for M1.
- ✅ **Wu et al. (2026), *Nature Neuroscience*, DOI 10.1038/s41593-026-02235-x** (NPY, above) — receptor-defined subpopulations gate *degree* of memory modification, supporting graded rather than all-or-none destabilization.

**Human evidence for selective editing is where it falls apart.**
- ◻︎ **Schiller, Monfils, Raio, Johnson, LeDoux & Phelps (2010), *Nature* 463:49–53, DOI 10.1038/nature08637** — peer-reviewed. Reactivation-then-extinction within the reconsolidation window prevented return of fear, **and critically was CS-specific**: only the reminded CS lost fear. This is the paper everyone cites for localized human reconsolidation.
- ✅ **Chalkia, Van Oudenhove & Beckers (2020), "Preventing the return of fear in humans using reconsolidation update mechanisms: A verification report of Schiller et al. (2010)," *Cortex* 129:510–525, DOI 10.1016/j.cortex.2020.03.031** — peer-reviewed **verification report on the original data.** Findings: exclusions were **misreported (6 claimed, 61 actual)**; ANOVAs and follow-up *t*-tests were mismatched; exclusion decisions were qualitative and unprincipled; there were physiologically implausible values and data-processing discrepancies. **All reported differences between reactivation-extinction and regular extinction were dependent on those qualitative exclusions.** The authors conclude the results are "unreliable and flawed" and should not be counted as evidence. There is a corrigendum (*Cortex* 2021, DOI 10.1016/j.cortex.2021.03.010) and a Schiller/LeDoux/Phelps reply plus a Chalkia et al. rejoinder ("The lack of evidence in Schiller et al. (2010) verified," 2021).

  **You must not cite Schiller 2010 as unqualified support.** If you cite it, cite the verification report in the same sentence.

- ✅ **Propranolol reconsolidation, clinical:** the widely-cited meta-analysis (*J. Psychiatry Neurosci.*, DOI 10.1503/jpn.210057) was followed by ✅ **"Updated and rectified meta-analysis shows no effect of propranolol versus placebo on traumatic memory reconsolidation disruption," *J. Psychiatry Neurosci.* (2022), DOI 10.1503/jpn.220072-l** — peer-reviewed. **Null.** (I could not fetch the full text — 403 — so pull the exact effect sizes yourself.) Also ✅ *Frontiers in Pharmacology* (2025), DOI 10.3389/fphar.2025.1545493, systematic review and meta-analysis of propranolol in PTSD.
- ✅ **"Demarcating the boundary conditions of memory reconsolidation: An unsuccessful replication," *Scientific Reports* 12 (2022), DOI 10.1038/s41598-022-06119-5** — peer-reviewed. Failed replication of the boundary-condition framework itself.

**What determines lability.** The consensus answer is **prediction error at retrieval** — enough mismatch to trigger updating, not so much that a new memory is formed instead:
- ◻︎ **Sevenster, Beckers & Kindt (2013), *Science* 339:830–833, DOI 10.1126/science.1231357** — peer-reviewed. PE is necessary for destabilization in humans.
- ◻︎ **Sinclair & Barense (2018), "Surprise and destabilize," *Learning & Memory* 25:369–381, DOI 10.1101/lm.046912.117** — peer-reviewed.
- ◻︎ **Fernández, Boccia & Pedreira (2016), *Neurosci. Biobehav. Rev.*, "The fate of memory: Reconsolidation and the case of Prediction Error"** — peer-reviewed review.
- ✅ **"Neurotransmitters in memory destabilization: An integrative perspective framed by prediction error and novelty," *Cognitive, Affective, & Behavioral Neuroscience* (2026), DOI 10.3758/s13415-026-01449-7** — peer-reviewed, current.
- ✅ **"Not the same as it ever was: A review of memory modification, updating, and distortion in humans and rodents," *Neurosci. Biobehav. Rev.* (2025), DOI 10.1016/j.neubiorev.2025.106xxx (PII S0149763425001952)** — peer-reviewed; robots.txt blocked me. **Read this one; it is the most current synthesis of exactly your question.**

### (b) Minimal computational abstraction licensed

A **conditional, scoped, time-windowed write-unlock**:

```
on retrieval of trace T with prediction error δ:
    if δ_low < δ < δ_high:              # too little → no unlock; too much → new trace
        unlock(scope(T, cue))            # scope = the reactivated input pathway only
        for τ in [0, W]:                 # bounded window
            T ← T + η·update
        relock(T)
```

The **scope** operator is what Doyère 2007 licenses: the unlocked set is the set of synapses on the *reactivated afferent pathway*, not the whole trace. In a network, that maps to "unlock the parameters that were causally involved in producing *this* retrieval, as identified by the retrieval's own activation pattern" — i.e. a retrieval-gated, path-scoped parameter mask.

**Honest caveat you should write into the proposal:** localized reconsolidation is well-supported at the level of *input pathway / associative element* in rodents, and poorly supported at the level of *arbitrary sub-component of a rich episodic memory* in humans. Your M1 is safe if it assumes the former. It is unsupported if it assumes the latter. **Say which one you mean, in the proposal, explicitly.**

### (c) Closest existing AI method

- **Model editing:** ROME (Meng, Bau, Andonian & Belinkov, NeurIPS 2022, arXiv:2202.05262), MEMIT (ICLR 2023, arXiv:2210.07229) — locate-then-edit; exactly "scoped write to the parameters causally responsible for this retrieval."
- **Task arithmetic / task vectors:** Ilharco et al., ICLR 2023, arXiv:2212.04089.
- ✅ **"Decomposing Task Vectors for Refined Model Editing" (2025), arXiv:2512.22511 — PREPRINT.** Directly on localized editing granularity.
- **Machine unlearning**; **LoRA-scoped fine-tuning**; **elastic weight consolidation** as the inverse (PROTECT).

**Gap vs. AI: small-to-negative.** ROME/MEMIT already do causally-scoped localized editing with better precision than the biology evidence supports. What ML lacks is the **trigger** — the principled, PE-gated *decision* to unlock, and the automatic relock. That trigger is your contribution, not the editing itself.

---

## 5. CONTEXT INFERENCE AND GATING

### (a) Strongest recent empirical findings

**Thalamocortical.**
- ✅ **Zheng, Wu, Hummos, Yang & Halassa (2024), *Nature Communications* 15, DOI 10.1038/s41467-024-52289-3** — peer-reviewed. **Computational model** (thalamocortical RNN) compared against mouse data. *Measured:* the MD module infers temporal context from PFC input within **~six trials (three cue-presentation cycles)**. Mechanism: Hebbian rule with pre/post activity traces, **winner-take-all normalization** in MD, and **adaptive thresholding** balancing fast learning of the current context against slow forgetting of previous ones. Enables sequential multi-task learning without catastrophic forgetting.
- ✅ **Zhang, Mukherjee, Halassa & Chen (2025), *Nature Communications*, DOI 10.1038/s41467-025-58011-1** — peer-reviewed. Biologically-constrained PFC-MD RNN with PV/VIP/SOM interneurons. *Measured:* PFC-MD beat PFC-alone under intermediate-to-high cue uncertainty (p = 0.00016); **~80% of MD units encoded cueing context, not rule**, while **55–65% of PFC excitatory units showed context-invariant rule tuning**; MD addition increased network time constant (p = 5×10⁻⁴⁸). Causal: MD1→PV weakening degraded performance rapidly; **restricting plasticity to thalamocortical/corticothalamic weights alone still supported rapid context switching**.

  That last result is the important one for you: **it is a factorization claim.** Context lives in the thalamic bottleneck; the rule lives in cortex; and you can switch context by writing only to the low-dimensional thalamic interface. That is exactly a hypernetwork / adapter-routing architecture, discovered independently by biology.

- ✅ **"Thalamocortical architectures for flexible cognition and efficient learning," *Trends in Cognitive Sciences* (2024), DOI 10.1016/j.tics.2024.05.006** (verify) — peer-reviewed review; Halassa lab framing.
- ✅ **"Thalamic regulation of reinforcement learning strategies across prefrontal-striatal networks," *Nature Communications* (2025), DOI 10.1038/s41467-025-63995-x** — peer-reviewed.

**Latent-cause / state inference.**
- ◻︎ **Gershman, Blei & Niv (2010), "Context, learning, and extinction," *Psychological Review* 117(1):197–209, DOI 10.1037/a0017808** — peer-reviewed. Canonical latent-cause account; extinction is new latent-cause learning, not unlearning. **This is the theoretical parent of your DESTABILIZE-vs-new-context decision.**
- ◻︎ **Gershman, Monfils, Norman & Niv (2017), *eLife* 6:e23763** — peer-reviewed. Latent-cause account of when reconsolidation vs. new learning occurs. **Directly relevant to your M1: it gives you a principled criterion for the unlock decision.**
- ✅ **"Reconciling shared versus context-specific information in a neural network model of latent causes," *Scientific Reports* 14 (2024), DOI 10.1038/s41598-024-64272-5** (arXiv:2312.08519) — peer-reviewed.
- ✅ **"The Ubiquity of Time in Latent-cause Inference" (2024), *J. Cognitive Neuroscience* / PMC11493367** — peer-reviewed. Time as the dominant cue for latent-cause segmentation.

**How fast do humans infer a switch — the number you asked for.**
- ✅ **Foucault, Weber & Hunt (2026), *eLife* reviewed preprint, DOI 10.7554/eLife.110137.1** — **reviewed preprint, v1 (Feb 2026), not yet version of record.** n = 30 per experiment (60 total), "capture-the-beams" prediction task. *Measured:* in change-point environments, large prediction errors triggered **sharp increases in learning rate**; in random-walk environments learning rates stayed stable. **100% of participants were better fit by the change-point model in the abrupt condition**, only 10% in the gradual condition. **Humans detected a variance change within ~3 observations.** Performance: 81% capture (change-point), 77% (random-walk).

  **~3 observations is the number to quote for human context-switch detection speed.** Flag it as a reviewed preprint.

- ✅ **"Computational processes of simultaneous learning of stochasticity and volatility in humans," *Nature Communications* 15 (2024), DOI 10.1038/s41467-024-53459-z** — peer-reviewed.
- ✅ **"A model for learning based on the joint estimation of stochasticity and volatility," *Nature Communications* 12 (2021), DOI 10.1038/s41467-021-26731-9** — peer-reviewed. **This one matters as a caveat:** much apparent volatility-tracking is confounded with stochasticity estimation, and the two must be jointly inferred. A reviewer who knows this will ask whether your "context switch detector" is really just a noise estimator.
- ◻︎ **Behrens, Woolrich, Walton & Rushworth (2007), *Nature Neuroscience* 10:1214–1221, DOI 10.1038/nn1954** — canonical ACC volatility signal.
- ✅ **"Two time scales of adaptation in human learning rates," *eLife* (2025/26), eLife 108223** — reviewed preprint; check status.

### (b) Minimal computational abstraction licensed

A **low-dimensional latent context variable *c* inferred online by approximate Bayesian filtering with a CRP-style prior over "new cause," which multiplicatively routes a fixed shared parameter set:**

```
c_t ~ p(c | x_{1:t}, c_{1:t-1})        # nonparametric prior: reuse old cause or spawn new
θ_eff = θ_shared ⊙ m(c_t)               # low-rank gate / adapter selection
```
with an **update rule whose learning rate is a function of posterior surprise**, and — the specifically biological addition from Zhang 2025 — **plasticity restricted to the c-interface** (the thalamocortical weights), leaving the shared cortical parameters untouched. Detection latency target: ~3–6 observations.

### (c) Closest existing AI method

- ◻︎ **Bayesian Online Changepoint Detection:** Adams & MacKay (2007), arXiv:0710.3742 — the exact algorithm.
- ◻︎ **Fearnhead & Liu (2007), *JRSS-B* 69(4):589–605** — peer-reviewed, online multiple changepoint.
- **Mixture-of-experts routing:** Shazeer et al. (2017), arXiv:1701.06538; Switch Transformer (Fedus, Zoph & Shazeer, JMLR 2022). ✅ Current surveys: arXiv:2503.07137, arXiv:2407.06204.
- **Hypernetworks:** Ha, Dai & Le (ICLR 2017, arXiv:1609.09106); **HNET continual learning** (von Oswald et al., ICLR 2020, arXiv:1906.00695).
- ✅ **Hummos, "Thalamus: a brain-inspired algorithm for biologically-plausible continual learning and disentangled representations," ICLR 2023, arXiv:2205.11713** — the direct AI instantiation of the thalamocortical result. **Cite this; it is the ML paper that already did your area-5 abstraction.**
- ✅ **Flesch, Nagy, Saxe & Summerfield, "Modelling continual learning in humans with Hebbian context gating and exponentially decaying task signals," *PLOS Computational Biology* (2023), DOI 10.1371/journal.pcbi.1010808** — peer-reviewed.

**Gap vs. AI: essentially zero.** BOCPD, MoE, hypernetworks and adapters collectively cover this abstraction completely, and Hummos 2023 already published the biologically-motivated version. **This is the area I would cut or demote.** See ranking below.

---

## 6. ASTROCYTES AND SLOW MEMORY STABILISATION

### (a) Strongest recent empirical findings

**Two Nature papers, both 2024/2025, both with real causal manipulations.**

- ✅ **Williamson, Kwon, … (2025), *Nature* 637:478–486, DOI 10.1038/s41586-024-08170-w** — peer-reviewed. Mice; intersectional c-Fos-based labeling of "learning-associated astrocytes" (LAAs) in hippocampus; chemogenetics, Ca²⁺ imaging, ephys, RNA-seq. *Measured:* learning drove c-Fos in an astrocyte subset (p < 0.0001); LAAs were spatially proximate to engram neurons; **chemogenetic reactivation of LAA ensembles was sufficient to elicit memory recall**; LAAs showed elevated NFIA, and **NFIA deletion from LAAs impaired recall (p = 0.014)**; LAA reactivation enhanced LTP (p = 0.007).

- ✅ **Dewa, Kaseda, Kuwahara, … Nagai (2025), *Nature*, DOI 10.1038/s41586-025-09619-2** — peer-reviewed. Mice, contextual fear conditioning; brain-wide serial two-photon tomography; Fos-iCreERT2 (TRAP2) × astrocyte-selective AAV-PHP.eB; scRNA-seq of amygdalar astrocytes; fiber photometry for NA/cAMP/Ca²⁺; conditional *Adra1a*/*Adrb1* knockouts. *Measured:* fear **recall** induced astrocytic Fos (fear-recall brain-wide astrocyte ensembles, FR-BAEs) at **>30× the density seen after conditioning itself**; conditioning upregulated *Adrb1*/*Adra1a* for **1–3 days**, peaking at day 1 — a genuine **multiday molecular trace**; FR-BAEs required coincident LC-noradrenergic input and local engram-neuron activity (silencing either reduced density ~50%); astrocyte-specific *Adrb1* or *Adra1a* KO reduced FR-BAE density 40–60%; *Adrb1* overexpression tripled FR-BAE density and enhanced stabilization under weak conditioning; downstream effector **IGFBP2**, and IGFBP2-neutralizing antibody post-recall reduced later freezing.

- ✅ **Sánchez Romero & Navarrete (2026), "Astroengrams: rethinking the cellular substrate for memory," *Nature Reviews Neuroscience*, DOI 10.1038/s41583-025-01012-2** — peer-reviewed review.

### How strong is this really — the sceptical read you asked for

**Solid:** astrocytes form sparse, learning-associated, pathway-specific ensembles; manipulating them changes recall and stabilization in both directions (necessity and sufficiency); there is a molecularly identified multiday window (1–3 days) with an identified effector (IGFBP2) and an identified gating input (LC noradrenaline). The two Nature papers converge from different directions using different labeling strategies. That is stronger than most "astrocytes do X" literature.

**Not solid, per the Nat Rev Neuro review's own accounting:** whether astrocyte reactivation is sufficient for *complete* recall is unresolved; the **relative contribution of astrocytic vs. neuronal components is unquantified**; whether astrocyte ensembles form before or after neuronal engagement is unknown; specificity across memory types and regions is untested.

**Confounds a hostile reviewer will raise, some of which the Dewa paper itself flags:**
1. **Fos-based tagging in astrocytes is a temporally coarse integrator (~hours) compared to a ~90 min scRNA-seq snapshot** — fold-change estimates may be inflated.
2. **Novelty confound.** Dewa et al. note that *without* habituation, contextual novelty alone drives widespread astrocytic Fos. The 30× recall-vs-conditioning asymmetry depends on a specific habituation protocol. That is a load-bearing methodological choice.
3. **Chemogenetic manipulation of astrocytes is notoriously non-specific** — Gq-DREADD activation of astrocytes produces broad, sometimes off-target effects on neuronal excitability, and there is a standing literature dispute about whether astrocytic Gq signaling is physiological. Williamson et al.'s sufficiency claim rests on this.
4. **Behavioral readout is freezing only.** Generalization untested.
5. **Only fear/contextual memory.** No spatial, episodic-like, or appetitive replication.

**Verdict: strong enough to cite as motivation, not strong enough to be a load-bearing mechanism family in a proposal whose thesis is a control plane.** The finding that licenses the least speculation — and the one you should actually use — is narrow: *there exists a slow (1–3 day), separately-gated, neuromodulator-triggered process that determines whether a recalled memory is re-stabilized.* That claim is well-supported. Every stronger claim ("astrocytes store memories," "astrocytes are a second memory substrate") is currently underdetermined.

### (b) Minimal computational abstraction licensed

A **second, slow, low-bandwidth state variable per memory unit, updated only at retrieval, gated by a global neuromodulatory signal, with a multi-day time constant, whose value sets the effective learning rate / write-protection of the fast weights.**

That is: `s_i(t+1) = s_i(t) + α·NA(t)·retrieved_i(t)`, decaying over days, with `η_i ∝ f(s_i)`. It is a **consolidation-scheduler / write-protect register**, not a memory store. Note carefully: the data support the astrocyte as a *modulator of whether the neuronal trace persists*, not as the trace.

### (c) Closest existing AI method

- **Synaptic Intelligence** (Zenke, Poole & Ganguli, ICML 2017, arXiv:1703.04200) — per-parameter importance accumulator; almost exactly the abstraction.
- **Elastic Weight Consolidation** (Kirkpatrick et al., *PNAS* 2017, DOI 10.1073/pnas.1611835114) — Fisher-weighted write protection.
- **Benna & Fusi (2016), *Nature Neuroscience* 19:1697–1706, DOI 10.1038/nn.4401** — peer-reviewed. Cascade/multi-timescale synaptic model. **This is the closest and it predates the astrocyte data by a decade.**
- **Fast weights / slow weights** (Ba, Hinton, Mnih, Leibo & Ionescu, NeurIPS 2016, arXiv:1610.06258).
- ✅ **Kozachkov, Slotine & Krotov, "Neuron-astrocyte associative memory," *PNAS* (2025), DOI 10.1073/pnas.2417788122; arXiv:2311.08135** — peer-reviewed. Astrocyte morphology/physiology yields a Dense Associative Memory (modern Hopfield) with **supralinear memory scaling**, outperforming all known biological DAM implementations. This is the one genuinely interesting AI-side astrocyte result — and note that Dense Associative Memory is the mathematical relative of transformer attention.
- ✅ **"RMAAT: Astrocyte-Inspired Memory Compression and Replay for Efficient Long-Context Transformers," arXiv:2601.00426 — PREPRINT.**

**Gap vs. AI: negative.** ML has had multi-timescale write-protection since Benna–Fusi 2016 and EWC 2017.

---

## 7. CROSS-CUTTING: THE HUMAN EFFICIENCY GAP

### (a) Strongest recent empirical findings

**The definitive quantification, and it is very recent.**
- ✅ **Tsividis, Loula, Burga, Rodriguez, Arnaud, Foss, Campero, Subramanian, Pouncy, Gershman & Tenenbaum (2026), "Human-level learning of complex novel tasks as theory-based modelling, exploration and planning," *Philosophical Transactions of the Royal Society A* 384(2320):20240529, DOI 10.1098/rsta.2024.0529** — peer-reviewed. **300 human participants, 90 novel video games**, 4–6 levels each. *Measured:* humans learned most games within **~a few hundred to ~1,000 in-game steps** (0.43 s/step). EMPA (theory-based Bayesian model learning in VGDL + theory-based curiosity for exploration + best-first planning) matched human efficiency on **79/90 games**, within 0.1×–10× on almost all, and beat humans on ~2/3. **DDQN was >100× less efficient on 67/90 games, >1000× worse on 45/90, >10,000× worse on 22/90. Rainbow was no better on average.** On 5 Atari games, EMPA hit ≥75% of mean human score on 4/5 within 21,000 frames (~6 min), where Rainbow and EfficientZero were "not statistically distinguishable from random play."

  **This is your headline number: 100×–10,000×, measured, peer-reviewed, 2026.**

**Priors, isolated by ablation.**
- ◻︎ **Dubey, Agrawal, Pathak, Griffiths & Efros (2018), "Investigating Human Priors for Playing Video Games," ICML, PMLR 80:1349–1357; arXiv:1802.10217** — peer-reviewed. Systematic ablation of visual/semantic priors (object-ness, affordance, similarity, "things that look like ladders can be climbed"). *Measured:* removing priors degraded human solving time **from ~2 minutes to over 20 minutes** — a ~10× slowdown. Priors are a large but **not sufficient** explanation: ablated humans were still far faster than RL agents.

**Developmental / causal.**
- ✅ **Goddu & Gopnik (2024), "The development of human causal learning and reasoning," *Nature Reviews Psychology* 3:319–339, DOI 10.1038/s44159-024-00300-5** — peer-reviewed. Current synthesis: children perform causal *intervention* (not just observation), form and test overhypotheses, and generate their own informative experiments.
- ◻︎ **Schulz (2012), "The origins of inquiry," *Trends in Cognitive Sciences* 16:382–389** — canonical on self-generated curricula.
- ◻︎ **Lake, Ullman, Tenenbaum & Gershman (2017), "Building machines that learn and think like people," *Behavioral and Brain Sciences* 40:e253, DOI 10.1017/S0140525X16001837** — peer-reviewed. The intuitive-physics/intuitive-psychology "start-up software" argument.

**The result that threatens your proposal's premise — read this one carefully.**
- ✅ **Csaba, Kumar, Tudor, Andrews, Hunt, Summerfield, Tenenbaum, Costa, Mattar & Tomov (2026), "Reason to Play: Behavioral and Brain Alignment Between Frontier LRMs and Human Game Learners," arXiv:2605.08019 — PREPRINT, not peer-reviewed.** 32 human adults (17M/15F), 8 frontier reasoning models tested zero-shot on novel VGDL games. *Measured:* best model (DeepSeek V4-Pro) reached discovery EMD 0.28 vs. human baseline — a **5–11× reduction in discovery EMD relative to deep-RL baselines** (DDQN 3.07, EfficientZero 3.22). LRMs solved **11–65%** of level-instances vs. **75%** for humans. LRM representations predicted fMRI BOLD **an order of magnitude better** than RL alternatives (r ≈ 0.07–0.10 in visual cortex vs. r = 0.015 for the best RL baseline), across all six ROIs tested.

  **The implication you must confront in the proposal: the sample-efficiency gap on interactive novel tasks is no longer primarily a plasticity problem — frontier LRMs close most of it with priors + in-context reasoning and no weight updates at all.** A reviewer will say: "You propose a plasticity-control plane to solve a gap that a frozen model with good priors already mostly closes." You need a task domain where that is false. Candidates: tasks requiring genuinely novel *procedural* skill acquisition, long-horizon tasks exceeding context, tasks with irreducible interference between sequentially-learned skills, and tasks where the agent must *retain* what it learned across sessions. **Choose your benchmarks so that in-context learning cannot substitute for weight change**, and say so explicitly in the proposal.

### (b) Minimal computational abstraction licensed

Human sample efficiency decomposes as roughly:
1. **Structured priors** (objects, agents, contact physics, goals) — ~10× per Dubey ablation.
2. **Hypothesis-space-restricted program induction** over a compositional model class — the largest single factor; EMPA gets ~all of human efficiency from this without any plasticity innovation.
3. **Theory-driven, epistemic exploration** — exploration targeting *unobserved interactions*, not state novelty.
4. **Planning in the induced model** rather than in raw state space.

**Honest answer to your plasticity-vs-priors question: the evidence overwhelmingly favours priors + inference over plasticity.** EMPA has no interesting plasticity — it is Bayesian model inference plus search — and it matches humans on 79/90 games. **Nothing in the current literature demonstrates that a better plasticity rule closes the interactive-learning gap.** This is the most important finding in this scan for your proposal, and it is the one a hostile reviewer will reach for first.

The defensible position is narrower and, I think, still fundable: *priors and in-context inference explain within-episode efficiency; they do not explain cross-episode retention, interference management, or the conversion of in-context discoveries into durable, composable skills.* That is a plasticity-control problem. Frame the proposal there.

### (c) Closest existing AI method

EMPA itself; ✅ **AXIOM (Verses AI, 2025, arXiv:2505.24784 — preprint)** — object-centric active inference with online structure learning, mastering arcade games in minutes; DreamerV3 (Hafner et al., *Nature* 2025, DOI 10.1038/s41586-025-08744-2); EfficientZero; and frontier LRMs with in-context learning.

---

## BLUNT ASSESSMENT AND RANKING

Scored on three axes: **(i) empirical strength**, **(ii) clarity of the minimal computational abstraction**, **(iii) gap vs. what ML already has.** The last column is what actually determines whether the proposal is field-defining or a re-derivation.

| # | Family | (i) Empirics | (ii) Abstraction clarity | (iii) Gap vs. ML | Verdict |
|---|---|---|---|---|---|
| 1 | **Inhibitory suppression / inhibitory engrams** (SUPPRESS) | Strong-moderate | High | **Large** | **Keep — make it the centrepiece** |
| 2 | **BTSP as gated one-shot write** (FAST_BIND) | Strong (CA1); weak elsewhere | High | **Moderate-large, if reframed** | **Keep — but reframe** |
| 3 | **Replay selection & recombination** (RETRIEVE / PREPLAY) | Strong for selection; strong-new for recombination; **weak for preplay** | High | Moderate (EVB exists) | **Keep — drop "preplay," keep recombination** |
| 4 | **Reconsolidation / localized editing** (DESTABILIZE / ROLLBACK) | **Rodent: good. Human: badly damaged.** | High | **Small — ROME/MEMIT already do it** | **Keep, but narrow and heavily caveated** |
| 5 | **Astrocytes / slow stabilisation** (CONSOLIDATE / PROTECT) | Moderate, two good Nature papers, real confounds | Moderate | **Negative — Benna-Fusi, EWC, SI** | **Drop as a mechanism family; retain one sentence as motivation** |
| 6 | **Context inference & gating** | Strong | Very high | **~Zero — BOCPD + MoE + hypernets + Hummos 2023** | **Drop as a contribution; keep as infrastructure** |

### Ranked by what should carry the proposal

**1st — Inhibitory suppression (SUPPRESS).** Best gap-to-evidence ratio in the whole scan. Liao et al. 2024 gives you inhibition performing *selection over what gets consolidated*, with a causal test. Wimber et al. 2015 gives you representation-specific, targeted suppression in humans. Barron et al. 2017 gives you the theoretical form. Vogels & Sprekeler 2011 gives you a working rule. And ML genuinely does not have learned, context-conditioned, *reversible* suppression of a specific memory — unlearning is destructive, steering is hand-specified. Build the proposal here.

**2nd — BTSP, reframed (FAST_BIND).** Strong empirics but only in CA1; the cortical extension is a preprint with a narrower window (−2 s to +0.5 s vs. ±5 s). If you frame it as "eligibility traces plus instructive signal," you lose — that is e-prop 2020 and RFLO 2019. If you frame it as **learned, sparse, top-down write-gating over a binary content-addressable store, with gate rate under novelty control**, you win: Wu & Maass 2025 shows the resulting memory system is not equivalent to Hopfield or to any standard rule (it uniquely reproduces the repulsion effect), and Madar et al. 2025 shows the gate rate is itself modulated. **The novel object is the gating policy, not the plasticity rule.** Say that explicitly.

**3rd — Replay, restricted to selection + compositional recombination.** He et al. 2026 (human iEEG, compositional recombination around ripples, predicts inferential behaviour) is the strongest single new result in your favour and it is exactly your PREPLAY primitive done right. Yang et al. 2024 gives you selection-at-encoding with R = 0.86. Frank et al. 2026 gives you uncertainty-gating in humans. But: prioritized replay exists, Mattar & Daw 2018 already gave the normative theory, and you must handle Deceuninck & Kloosterman's null, Widloski & Foster's ripple/replay dissociation, Thompson et al.'s hippocampus-independent replay, and Takigawa et al.'s false-positive-rate critique. **Explicitly cut rodent "preplay"** — Silva/Feng/Foster 2015 versus Dragoi & Tonegawa 2011 is an unresolved fight you do not need to be in, and you don't need it because the human compositional result is better.

**4th — Reconsolidation, narrowed (DESTABILIZE / ROLLBACK).** Your M1 assumption *is* supported, but only at one grain size: **Doyère et al. 2007 shows input-pathway-specific, synapse-localized reconsolidation, measured directly.** That is real and it is your citation. What is *not* supported is arbitrary component-level editing of rich human memories — and the flagship human paper for that, Schiller et al. 2010, was materially undermined by the Chalkia et al. 2020 verification report (61 undisclosed exclusions; all key differences contingent on unprincipled exclusions), and the propranolol clinical literature has a rectified null meta-analysis. **Rewrite M1 to assume pathway-scoped, retrieval-gated unlock, cite Doyère, cite the Chalkia verification report yourself before a reviewer does, and drop any claim that human reconsolidation supports selective editing.** Also note the gap here is small — ROME and MEMIT already do causally-scoped localized editing. Your contribution is the *unlock trigger* (PE-gated, with Gershman et al. 2017's latent-cause criterion for reconsolidate-vs-new-trace), not the edit.

**5th — DROP: Astrocytes.** Not because the science is bad — the two Nature papers are good and Dewa et al.'s multiday *Adrb1*/*Adra1a* window with IGFBP2 as effector is a genuinely nice result. Drop it because **the abstraction it licenses is a slow per-parameter write-protect register, and ML has had that since Benna & Fusi 2016, EWC 2017 and Synaptic Intelligence 2017.** Adding astrocytes buys you biological novelty and zero computational novelty, while importing real methodological liabilities (astrocytic Gq-DREADD non-specificity, Fos-tagging temporal coarseness, novelty confounds, freezing-only readout, fear-memory-only). Keep one motivating sentence citing Dewa et al. for the existence of a multiday stabilization window. Do not make it a mechanism family. (The one exception worth a footnote: Kozachkov, Slotine & Krotov's supralinear Dense Associative Memory scaling is a real computational claim — but it is an architecture result, not a plasticity-control result, and it doesn't belong in your control plane.)

**6th — DEMOTE: Context inference and gating.** The neuroscience is excellent and the abstraction is crystal clear, which is precisely the problem: **it is completely covered.** Adams & MacKay 2007 is BOCPD. Shazeer 2017 and Switch are MoE routing. Ha et al. 2017 and von Oswald et al. 2020 are hypernetworks for continual learning. Ilharco et al. 2023 is task vectors. And Hummos's ICLR 2023 "Thalamus" already published the biologically-motivated thalamocortical version of exactly this. **You cannot claim novelty here.** But you should keep it as *infrastructure*: your control plane needs a context signal to condition SUPPRESS masks and to decide DESTABILIZE-vs-new-trace, and the Zhang et al. 2025 result that restricting plasticity to the thalamocortical interface alone suffices for rapid switching is a clean architectural justification for making your control plane a low-rank adapter over frozen shared parameters. Use it as a design constraint, not a contribution. Useful number to quote: humans detect a change within ~3 observations (Foucault et al., eLife reviewed preprint 2026).

### The three things most likely to sink the proposal

1. **"Reason to Play" (arXiv:2605.08019).** Frontier LRMs already achieve a 5–11× discovery-efficiency improvement over deep RL on novel games with zero weight updates, and align to human fMRI an order of magnitude better than RL. Your premise — that the human-AI interactive-learning gap is a plasticity problem — is empirically contested as of 2026. **Pick benchmarks where in-context learning provably cannot substitute for weight change** (cross-session retention, interference between sequentially acquired skills, horizons exceeding context), and argue the point head-on in the introduction rather than letting a reviewer raise it.

2. **EMPA.** Tsividis et al. 2026 match human efficiency on 79/90 games using Bayesian theory induction and search, with no plasticity innovation at all. The strongest current explanation for human sample efficiency is **priors and structured inference, not plasticity.** If your proposal implies otherwise, it contradicts the best available measurement. Concede this and reposition: plasticity control governs what *survives* and *composes* across episodes, not within-episode speed.

3. **Chalkia et al. 2020.** If a reviewer knows the reconsolidation literature, they know Schiller et al. 2010 was materially undermined and the propranolol clinical meta-analysis was rectified to null. Cite the verification report yourself, and anchor localized editing on Doyère et al. 2007 (rodent, synapse-resolved, unimpeached) instead.

### One structural suggestion

Your eight primitives are not equally supported and they are not the same kind of thing. RETRIEVE, PREPLAY, SUPPRESS and FAST_BIND are **inference-time operations with direct neural correlates**. CONSOLIDATE, PROTECT, DESTABILIZE and ROLLBACK are **offline/scheduling operations that ML already has under other names** (EWC, SI, model editing, checkpointing). Consider collapsing the second group into a single "write-schedule" mechanism and spending the saved space on the gating *policy* that selects among the first group — because the policy, not the primitives, is the part nobody has.

---

## Sources

Replay and ripples: [Yang et al., Science 2024](https://www.science.org/doi/10.1126/science.adk8261) · [He et al., Nat Neurosci 2026](https://www.nature.com/articles/s41593-026-02291-3) · [Frank et al., Nat Neurosci 2026](https://www.nature.com/articles/s41593-026-02345-6) · [Zhang, Ou & Liu, Annu Rev Neurosci 2025](https://www.annualreviews.org/content/journals/10.1146/annurev-neuro-112723-024516) · [Deceuninck & Kloosterman, eLife 2024](https://elifesciences.org/articles/84004) · [Widloski & Foster, Nat Commun 2025](https://www.nature.com/articles/s41467-025-65181-5) · [Thompson et al., Nat Neurosci 2026](https://www.nature.com/articles/s41593-026-02362-5) · [Takigawa et al., eLife 2024](https://elifesciences.org/articles/85635) · [Silva, Feng & Foster, Nat Neurosci 2015](https://www.nature.com/articles/nn.4151) · [Grosmark & Buzsáki, Science 2016](https://www.science.org/doi/10.1126/science.aad1935) · [Liu et al., Science 2021](https://www.science.org/doi/10.1126/science.abf1357) · [Liu et al., Cell 2019](https://www.cell.com/cell/fulltext/S0092-8674(19)30640-3) · [Human ripples prioritise model-based learning, bioRxiv 2025](https://www.biorxiv.org/content/10.1101/2025.07.31.667862v1.full) · [Ripples align with grid-like schema, Neuron 2025](https://www.cell.com/neuron/fulltext/S0896-6273(25)00555-0) · [Dopamine and replay localization, eLife](https://elifesciences.org/articles/99678)

BTSP: [Magee, Nat Neurosci 2026](https://www.nature.com/articles/s41593-026-02214-2) · [Madar et al., J Neurosci 2025](https://www.jneurosci.org/content/45/46/e1332252025) · [Madar et al., Nat Neurosci 2025](https://www.nature.com/articles/s41593-025-01894-6) · [Bittner et al., Science 2017](https://www.science.org/doi/10.1126/science.aan3846) · [Neocortical BTSP preprint, bioRxiv 2025](https://www.biorxiv.org/content/10.1101/2025.11.07.687250v1) · [Wu & Maass, Nat Commun 2025](https://www.nature.com/articles/s41467-024-55563-6) · [CaMKII in BTSP, Sci Adv](https://www.science.org/doi/10.1126/sciadv.adi3088) · [Bellec et al., Nat Commun 2020](https://www.nature.com/articles/s41467-020-17236-y) · [Three-factor learning survey, Patterns 2025](https://www.cell.com/patterns/fulltext/S2666-3899(25)00262-4)

Inhibition and suppression: [Liao et al., Nat Neurosci 2024](https://www.nature.com/articles/s41593-024-01745-w) · [Favila et al., Nat Commun 2025](https://www.nature.com/articles/s41467-025-66122-y) · [Wu et al., Nat Neurosci 2026 (NPY)](https://www.nature.com/articles/s41593-026-02235-x) · [Barron et al., PNAS 2017](https://www.pnas.org/doi/10.1073/pnas.1701812114) · [Wimber et al., Nat Neurosci 2015](https://www.nature.com/articles/nn.3973) · [Schmitz & Anderson, Nat Commun 2017](https://www.nature.com/articles/s41467-017-00956-z) · [Hulbert et al., Nat Commun 2016](https://www.nature.com/articles/ncomms11003) · [Vogels & Sprekeler, Science 2011](https://www.science.org/doi/10.1126/science.1211095) · [Engram competition, Trends Neurosci 2025](https://www.cell.com/trends/neurosciences/fulltext/S0166-2236(25)00153-5) · [DG inhibitory tone, PLOS Biol 2025](https://journals.plos.org/plosbiology/article?id=10.1371%2Fjournal.pbio.3003956) · [Downstream suppression of competitors, PNAS 2025](https://www.pnas.org/doi/10.1073/pnas.2410101122) · [Niczyporuk, Psychon Bull Rev 2025](https://link.springer.com/article/10.3758/s13423-025-02763-w) · [TNT multiverse analysis, Memory 2020](https://www.tandfonline.com/doi/full/10.1080/09658211.2020.1797095) · [Pre-registered TNT replication, Memory 2023](https://www.tandfonline.com/doi/full/10.1080/09658211.2023.2208791) · [Wessel et al., Top Cogn Sci 2024](https://onlinelibrary.wiley.com/doi/full/10.1111/tops.12684)

Reconsolidation: [Doyère et al., Nat Neurosci 2007](https://www.nature.com/articles/nn1871) · [Chalkia et al., Cortex 2020 verification report](https://pmc.ncbi.nlm.nih.gov/articles/PMC7115860) · [Corrigendum, Cortex 2021](https://www.sciencedirect.com/science/article/pii/S0010945221001064) · [Rectified propranolol meta-analysis, JPN 2022](https://cdnsciencepub.com/doi/10.1503/jpn.220072-l) · [Propranolol PTSD review, Front Pharmacol 2025](https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2025.1545493/full) · [Unsuccessful boundary-condition replication, Sci Rep 2022](https://www.nature.com/articles/s41598-022-06119-5) · [Memory modification review, Neurosci Biobehav Rev 2025](https://www.sciencedirect.com/science/article/abs/pii/S0149763425001952) · [Systems reconsolidation engram, Neuron 2024](https://www.cell.com/neuron/abstract/S0896-6273(24)00835-3) · [Destabilization neurotransmitters, CABN 2026](https://link.springer.com/article/10.3758/s13415-026-01449-7) · [Sinclair & Barense, Learn Mem 2018](https://learnmem.cshlp.org/content/25/8/369)

Context inference: [Zheng et al., Nat Commun 2024](https://www.nature.com/articles/s41467-024-52289-3) · [Zhang et al., Nat Commun 2025](https://www.nature.com/articles/s41467-025-58011-1) · [Thalamocortical architectures, Trends Cogn Sci 2024](https://www.cell.com/trends/cognitive-sciences/fulltext/S1364-6613(24)00119-0) · [Thalamic regulation of RL strategies, Nat Commun 2025](https://www.nature.com/articles/s41467-025-63995-x) · [Foucault et al., eLife reviewed preprint 2026](https://elifesciences.org/reviewed-preprints/110137) · [Stochasticity and volatility, Nat Commun 2024](https://www.nature.com/articles/s41467-024-53459-z) · [Joint estimation model, Nat Commun 2021](https://www.nature.com/articles/s41467-021-26731-9) · [Latent causes NN model, Sci Rep 2024](https://www.nature.com/articles/s41598-024-64272-5) · [Gershman, Blei & Niv, Psych Rev 2010](https://www.princeton.edu/~yael/Publications/GershmanEtAl2009.pdf) · [Hebbian context gating, PLOS Comput Biol 2023](https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1010808)

Astrocytes: [Williamson et al., Nature 2025](https://www.nature.com/articles/s41586-024-08170-w) · [Dewa et al., Nature 2025](https://www.nature.com/articles/s41586-025-09619-2) · [Astroengrams review, Nat Rev Neurosci 2026](https://www.nature.com/articles/s41583-025-01012-2) · [Kozachkov et al., PNAS 2025](https://www.pnas.org/doi/10.1073/pnas.2417788122) · [arXiv:2311.08135](https://arxiv.org/abs/2311.08135)

Human efficiency gap: [Tsividis et al., Phil Trans R Soc A 2026](https://gershmanlab.com/pubs/Tsividis26.pdf) · [Csaba et al., arXiv 2026 preprint](https://arxiv.org/html/2605.08019) · [Dubey et al., ICML 2018](https://arxiv.org/abs/1802.10217) · [Goddu & Gopnik, Nat Rev Psychol 2024](https://www.nature.com/articles/s44159-024-00300-5) · [AXIOM](https://www.verses.ai/research-blog/axiom-mastering-arcade-games-in-minutes-with-active-inference-and-structure-learning)