# ARC-AGI-3 Plasticity Lab

Discovering whether brain-inspired plasticity-control operations produce a reusable learning
primitive, measured on ARC-AGI-3 offline environments and purpose-built procedural families.

- Science: `PROPOSAL_v2.md`
- Process: `AGENT_CONSTITUTION.md`
- External ground truth: `docs/EVIDENCE_ARC.md`, `docs/EVIDENCE_NEURO.md`, `docs/EVIDENCE_TOOLING.md`
- Current position: `state/PROJECT_STATE.json`
- History: `state/LEDGER.jsonl`, `reports/DIGEST_*.md`

Licence: MIT-0.

## Run

```bash
uv sync
ARC_API_KEY=... uv run python scripts/warm_environment_cache.py   # once, needs network
uv run pytest                                                      # must pass before anything
python3 scripts/supervisor.py                                      # the autonomous loop
```
