# ESCALATION — G3.5, constitution section 6 item 1 (a credential is needed)

Written 2026-09-04T20:58Z at commit 90fbe1b (this turn's commit follows). Gate G3, task G3.5.

**How to answer:** append a section to THIS file beginning with a line `## ANSWER` and commit
or leave it in the working tree. Nothing else counts (not a chat message, not an edit
elsewhere). The supervisor and the next turn check for that line; on finding it the file is
moved to `state/escalations/<timestamp>.md`, `blocked_on` is cleared, and work resumes.

## What is needed

The reference architecture's model calls run as `claude -p` subprocesses started by
`scripts/run_experiment.py` from inside a supervisor turn (pre-registration G3
`model_calls.channel`). The adapter now exists (`src/arc_plasticity/agents/model_client.py`,
`HeadlessCliClient`) and the probe pre-registered under `escalation_plan.ordering` was run
this turn: one call, prompt `ping`, model `claude-fable-5-1`, effort `low`, tools disabled,
cwd a temporary directory, from inside this turn. It failed authentication:

```
exit_code 1, 0.77 s, stderr empty
stdout JSON: is_error true, subtype "success", terminal_reason "api_error",
             result "Not logged in · Please run /login", usage all 0, total_cost_usd 0
```

This matches the G3.1 observation: the turn's shell carries no `CLAUDE_CODE_OAUTH_TOKEN`
(the supervisor's token sustains the turn but is stripped from child processes) and
`claude auth status` reports `loggedIn false`. No amount of debugging produces a credential,
so this is escalated as planned rather than climbed under the ladder.

The three asks are the ones fixed in the pre-registration
(`escalation_plan.item_1_escalation_asks`):

1. **A credential route for runner-spawned calls, and confirmation that the subscription is
   the intended payer.** Two routes are implemented or available; either works:
   - **(a) Token file outside the repository.** Put the long-lived token from
     `claude setup-token` into a file such as `~/.arc_plasticity/claude_oauth_token`
     (any path outside `/home/afazeli2006/ARC_AGI3_Plasticity_Lab`, mode 600). Tell me the
     path. I will set `runner_params.model_client.token_file` to it in
     `configs/experiments/E300_ref.yaml`; the adapter reads it once per run, exports it to the
     child process only, and never writes it to any artifact (tests pin this). This changes
     the E300 config hash before the first graded run, which is allowed and re-recorded.
   - **(b) Pass-through from the supervisor.** Make `scripts/supervisor.py` (frozen; your
     edit) export `CLAUDE_CODE_OAUTH_TOKEN` into the turn's child environment. The adapter
     already forwards the turn environment minus `ARC_*` and the nested-session markers
     (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`), so nothing else is needed.
   An API key would be a paid service and is not asked for (section 6 item 2).

2. **The weekly-allowance denominator for the cost pre-flight** (`cost_preflight`), in any
   form you can read: the seven-day `used_percentage` from an interactive `/usage` view or
   the claude.ai usage page at the time of the answer, and, if known, the plan's weekly
   allowance in list-price USD equivalent. If you prefer the delta method, give me one reading
   now and I will ask for a second after the three pre-flight games (cd82, s5i5, wa30). The
   gauge never fires in headless mode and the CLI has no usage query, so I cannot obtain this.

3. **Optionally, a different model identifier** for the REF's calls if you want a cheaper one
   than `claude-fable-5-1` (the pre-registered default). Its list prices are then added to
   `docs/EVIDENCE_TOOLING.md` section 1 with a URL and date before any call.

## What was tried

- G3.1: `claude auth status` inside a turn (`loggedIn false`, no token in `env`).
- G3.5 (this turn): the adapter with a fake `claude` (14 unit tests) and the real probe above.
  The CLI accepted every flag; only authentication failed.

## What happens with each answer (pre-registered, `escalation_plan.what_happens_with_each_answer`)

- **Credential supplied** (route a or b): the adapter is pointed at it, the probe is repeated
  and its usage logged in the ledger, then the three pre-flight game-runs start
  (`cost_preflight.games`, graded configuration, `run set role preflight_graded`).
- **Credential refused, or an API key with a spend cap offered:** section 6 item 2 (money) is
  raised in this thread before any call; without either, G3 cannot run as pre-registered and
  you decide between waiting and a route change (section 6 item 12).
- **Denominator supplied:** `cost_preflight.decision_rule` applies mechanically after the
  three runs (escalate above 0.35 of the weekly allowance).
- **No denominator:** `cost_preflight.no_denominator_rule` applies: the pre-flight escalates
  unconditionally with the absolute numbers after the three runs.

Nothing under `artifacts/E300_ref/` exists yet and nothing will be created before this is
answered. The model-free components (E310, planner, accounting, runner, adapter) are complete
and tested: pytest 444 passed 2 skipped at this turn's commit.
