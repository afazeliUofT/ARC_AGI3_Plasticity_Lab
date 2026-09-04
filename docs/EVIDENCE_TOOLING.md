# Evidence Base, Part C: Tooling Fact Sheet

**Status:** compiled 2026-09-04 from official Claude documentation.
**Companion documents:** `EVIDENCE_ARC.md` (benchmark), `EVIDENCE_NEURO.md` (science).

**Authority and its limit.** This is the project's ground truth for the machinery it runs on:
model identifiers, CLI flags, permissions, hooks, subscription limits and authentication. It
was compiled by reading documentation, **not by running commands on the target machine.** That
distinction matters more here than in the other two evidence documents, because a wrong CLI
flag produces a failed setup rather than a wrong belief.

Every claim below carries one of three marks:

| Mark | Meaning |
|---|---|
| **[DOC]** | Stated in official documentation retrieved 2026-09-04. |
| **[UNCONFIRMED]** | Not found in documentation, or documented only for a different mode than the one this project uses. **Treat as a hypothesis.** |
| **[VERIFY-ON-MACHINE]** | Load-bearing enough that bootstrap must confirm it empirically before the supervisor is allowed to start. |

**Bootstrap obligation.** `scripts/verify_environment.py` must check every
[VERIFY-ON-MACHINE] item against the real installation and write the observed values back into
this file with the date. Until it has, treat this document as provisional.

---

## 1. Model

| Property | Value | Mark |
|---|---|---|
| API model ID | `claude-fable-5-1` | [DOC] |
| Context window | 1M tokens | [DOC] |
| Max output | 128K tokens | [DOC] |
| Thinking | adaptive, always on | [DOC] |
| Default effort | `high` | [DOC] |
| Per-message effort | supported, beta; does not invalidate the prompt cache | [DOC] |
| List price | $10 / MTok input, $50 / MTok output | [DOC] |
| Cache reads | $0.25 / MTok | [DOC] |
| Cache writes | $12.50 / MTok at 5 min, $20 / MTok at 1 h | [DOC] |
| Knowledge cutoff | June 2026 | [DOC] |
| Breaking change from Fable 5 | **forced tool use returns an error** | [DOC] |
| Thinking-block portability | thinking blocks are tied to the producing model; editing an earlier turn invalidates them | [DOC] |

Source: [platform.claude.com/docs/en/models/fable-5-1/overview](https://platform.claude.com/docs/en/models/fable-5-1/overview)

> **On price.** The list price is what an API-key user pays. On a Max subscription no
> per-token bill is incurred, but the *rate* at which the allowance is consumed still scales
> with tokens, so the price column is the right proxy for "how fast am I burning the window."

---

## 2. Headless invocation

| Item | Value | Mark |
|---|---|---|
| Non-interactive flag | `-p` / `--print` | [DOC] |
| Output formats | `text` (default), `json`, `stream-json` | [DOC] |
| JSON fields | `result`, `session_id`, `total_cost_usd`, `model_cost_breakdown` | [DOC] |
| Structured output | `--json-schema '<schema>'`, response carries `structured_output` | [DOC] |
| Model selection | `--model claude-fable-5-1` | [DOC] |
| Effort | `--effort low\|medium\|high\|xhigh\|max\|ultracode` | [DOC] **[VERIFY-ON-MACHINE]** — confirm the accepted set with `claude --help` |
| System prompt | `--append-system-prompt`, `--append-system-prompt-file`, `--system-prompt`, `--system-prompt-file` | [DOC] |
| stdin | supported, 10 MB cap | [DOC] |
| Turn cap | **no `--max-turns` flag found** | [UNCONFIRMED] |
| Exit codes | 0 success, non-zero failure, 143 on SIGTERM | [DOC] |
| Context exhaustion in headless | behaviour not documented; no confirmed auto-compaction | [UNCONFIRMED] **[VERIFY-ON-MACHINE]** |

**`--bare` must not be used.** It requires an API key and does not read
`CLAUDE_CODE_OAUTH_TOKEN` [DOC], and it disables auto-discovery of hooks, skills, subagents,
plugins, MCP servers and `CLAUDE.md` [DOC] — all of which this design depends on.

Source: [code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless)

---

## 3. Sessions

| Item | Value | Mark |
|---|---|---|
| Resume most recent in cwd | `--continue` | [DOC] |
| Resume by id or name | `--resume <session-id\|name>` | [DOC] |
| Branch a session | `--fork-session` | [DOC] |
| Storage | `~/.claude/projects/<project>/<session-id>.jsonl` | [DOC] |
| Survives reboot | yes | [DOC] |
| Retention | 30 days, `cleanupPeriodDays` | [DOC] |
| Relocate config | `CLAUDE_CONFIG_DIR` | [DOC] |

Both `--continue` and `--resume` work with `-p` [DOC].

Source: [code.claude.com/docs/en/sessions](https://code.claude.com/docs/en/sessions)

---

## 4. Permissions

Modes [DOC]: `default`, `auto`, `plan`, `acceptEdits`, `bypassPermissions`, selected with
`--permission-mode <mode>` or the `defaultMode` settings key.

`--permission-prompts none` [DOC] denies any action that would prompt a person; denials surface
as `permission_denied` system messages. **This is the correct flag for unattended operation** —
it fails closed rather than hanging.

`--dangerously-skip-permissions` [UNCONFIRMED] — referenced in the changelog but its current
exact name and restrictions were not found in the September 2026 documentation. **This project
does not use it.** A scoped allowlist plus `--permission-prompts none` achieves unattended
operation without disabling the safety surface the anti-self-deception controls rely on.

Rule syntax [DOC]: `Bash`, `Bash(git *)`, `Bash(git commit:*)`, `Read(/path/**)`,
`WebFetch(domain:example.com)`, `Agent(Explore)`.

Settings precedence, lowest to highest [DOC]: managed → `~/.claude/settings.json` →
`.claude/settings.json` → `.claude/settings.local.json` → `--settings`.

Permission keys [DOC]: `defaultMode`, `allow`, `ask`, `deny`, `additionalDirectories`,
`blockReadsOutsideWorkingDirectories`, `disableBypassPermissionsMode`.

Sandboxing [DOC]: the Bash tool supports optional sandboxing on macOS and Linux, and in WSL 2
sessions. **Not supported on native Windows.** This is a reason to prefer WSL for this project.

Sources: [permissions](https://code.claude.com/docs/en/permissions),
[permission-modes](https://code.claude.com/docs/en/permission-modes),
[settings-reference](https://code.claude.com/docs/en/settings-reference)

---

## 5. Hooks

Events [DOC]: `SessionStart`, `SessionEnd`, `Setup`, `UserPromptSubmit`, `Stop`, `StopFailure`,
`PreToolUse`, `PostToolUse`, `PermissionRequest`, `PreModelSwitch`, `PostModelSwitch`,
`FileChanged`, `CwdChanged`, `ConfigChange`, `Notification`, `SubagentStart`, `Elicitation`.

Input on stdin [DOC] carries `session_id`, `prompt_id`, `transcript_path`, `cwd`,
`permission_mode`, `hook_event_name`, `effort`, `agent_id`, `agent_type`.

Blocking a tool call [DOC]: exit code 2, with

```json
{"hookSpecificOutput":{"hookEventName":"PreToolUse",
 "permissionDecision":"deny","permissionDecisionReason":"..."}}
```

Handler types [DOC]: `command`, `http`, `mcp_tool`, `prompt`, `agent`. No restart required.

> **[UNCONFIRMED] and load-bearing:** no documented field lets a `Stop` hook force the agent to
> keep working, and no `stop_hook_active` loop guard was found. **This is why continuation is
> the supervisor's job and not a hook's.** Do not build the loop on a Stop hook.

> **Matcher scope matters for the anti-tamper controls.** A `PreToolUse` hook matching only
> `Write` and `Edit` does not intercept `Bash`. A hook that protects a file must match `Bash`
> as well and deny the shell patterns that write files (`sed -i`, `tee`, `python -c`, `>`,
> `cp`, `mv`, `truncate`, `git checkout --`). Verified reasoning, not a documentation claim —
> mark **[VERIFY-ON-MACHINE]**.

Source: [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)

---

## 6. Subagents

Location [DOC]: `.claude/agents/*.md` (project) or `~/.claude/agents/*.md` (user).
Frontmatter keys [DOC]: `name`, `description`, `tools`, `disallowedTools`, `model`,
`permissionMode`, `memory`, `maxTurns`, `isolation`, `hooks`, `skills`, `mcpServers`.

Subagents get an isolated context and do not see the parent conversation history [DOC].
Whether the context window is fresh or a compressed inheritance is [UNCONFIRMED]; the design
does not depend on which.

Source: [code.claude.com/docs/en/sub-agents](https://code.claude.com/docs/en/sub-agents)

---

## 7. Subscription limits — the part the supervisor depends on

**Windows.** A Max subscription meters a rolling **5-hour** window and a rolling **7-day**
window, and the allowance is **shared across Claude Code, Claude chat and Cowork** [DOC].
Usage spent in a browser chat reduces what the autonomous run has available.

**The gauge.** The status line receives JSON on stdin containing [DOC]:

```json
{"rate_limits":{
   "five_hour": {"used_percentage": 23.5, "resets_at": 1738425600},
   "seven_day": {"used_percentage": 41.2, "resets_at": 1738857600},
   "spend_limit":{"used_percentage": 62.8, "resets_at": 1740787200}}}
```

`resets_at` is **Unix epoch seconds** [DOC]. Both fields are **absent until the first API
response of a session** [DOC], so a probe must tolerate their absence.

> **[UNCONFIRMED] and the single most important gap in this document:** whether the status line
> fires at all in headless `-p` mode. Documented for interactive sessions; not documented for
> headless. **[VERIFY-ON-MACHINE]** — bootstrap installs `scripts/statusline_probe.sh`, runs one
> headless turn, and checks whether `state/usage.json` appears. The supervisor's behaviour
> branches on the answer, and both branches are implemented.

**`total_cost_usd` is null or absent under subscription auth** [DOC]. It is populated only for
API-key auth. **Do not use it to estimate remaining allowance** — it is a client-side list-price
estimate of spend, not a quota reading.

**Model-specific allowances** [UNCONFIRMED]: documentation does not say whether Fable 5.1 is
metered separately from other models within a Max plan, nor whether the CLI can fall back to a
cheaper model when one allowance is exhausted. **Working assumption: one shared seat allowance,
no automatic downgrade.** Do not design around a fallback that may not exist.

**Rate-limit failure signature** [UNCONFIRMED] **[VERIFY-ON-MACHINE]**: the error message is
reported as `You've hit your session limit` (5-hour) or `You've hit your weekly limit`
(7-day) [DOC, error reference], but the **exit code, whether the message is structured JSON,
and whether it carries a reset timestamp are all undocumented.** Bootstrap must capture the
real signature — the cheapest way is to record every non-zero exit verbatim into
`state/tool_errors.jsonl` from the first day, so the first real rate limit teaches the
supervisor its own signature. Until then the supervisor classifies by string match with
substring tolerance and treats any unclassified non-zero exit conservatively as retryable.

**Telemetry** [DOC]: `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_METRICS_EXPORTER`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, metrics `claude_code.cost.usage`, `claude_code.token.usage`,
`claude_code.session.count`, `claude_code.active_time.total`. **These report what was spent,
not what remains** — they do not solve the gauge problem [UNCONFIRMED that any OTEL metric
exposes remaining quota].

Sources: [costs](https://code.claude.com/docs/en/costs),
[statusline](https://code.claude.com/docs/en/statusline),
[monitoring-usage](https://code.claude.com/docs/en/monitoring-usage),
[errors](https://code.claude.com/docs/en/errors)

---

## 8. Authentication for multi-day runs

A cached subscription login is stored in `~/.claude/.credentials.json` [DOC] and **expires**;
Claude Code warns in advance ("Your login expires in 3 days") and then fails every request with
`Login expired · Please run /login` [DOC]. **There is no automatic refresh after expiry.** An
unattended run authenticated this way will die.

The fix [DOC]: `claude setup-token` generates a long-lived (approximately one-year) token,
exported as `CLAUDE_CODE_OAUTH_TOKEN`. It makes model requests only — not connectors, not
Remote Control — which is all this project needs. **[VERIFY-ON-MACHINE]:** confirm the token is
generated, exported in the supervisor's environment, and that a headless turn succeeds with the
interactive session logged out.

**Three failures the supervisor must distinguish, because the correct response differs:**

| Signature | Meaning | Response |
|---|---|---|
| `You've hit your session limit` / `weekly limit` | usage window exhausted | sleep until reset, resume |
| `Login expired` / `profile login expired` | auth gone | **escalate to human** — constitution §6 item 1 |
| HTTP 529, 500, timeout | transient service error | retry with exponential backoff |
| anything else, non-zero | unknown | log verbatim, retry once, then escalate |

---

## 9. Installation

| Platform | Command | Mark |
|---|---|---|
| Windows PowerShell | `irm https://claude.ai/install.ps1 \| iex` | [DOC] |
| macOS / Linux / WSL | `curl -fsSL https://claude.ai/install.sh \| bash` | [DOC] |
| npm (any) | `npm install -g @anthropic-ai/claude-code` — **Node.js 22+** | [DOC] |

Native Windows is fully supported [DOC] but uses PowerShell rather than Bash unless Git Bash is
present (`CLAUDE_CODE_GIT_BASH_PATH`), and **Bash sandboxing is unavailable on native Windows**
[DOC]. WSL 2 has full support including sandboxing [DOC].

Known WSL issues [DOC]: working on Windows paths from inside WSL is slow — clone inside the
distribution; workspace trust is granted per distribution-and-folder pair; Alpine/musl needs
`libgcc`, `libstdc++`, `ripgrep` and `USE_BUILTIN_RIPGREP=0`.

Source: [code.claude.com/docs/en/setup](https://code.claude.com/docs/en/setup)

---

## 10. What the programme actually consumes — and why "free" is the wrong word

The ARC environment simulator is free: `OperationMode.OFFLINE`, no key, no rate limit, ~2,000
FPS (`EVIDENCE_ARC.md` §3.1). **The agent is not free**, and it is the binding constraint on
the whole programme.

The reference architecture the project must build (`PROPOSAL_v2.md` §9, G3) is the same class
of system as the published state of the art, and those cost **$5,780 to $15,200 per run in API
calls** for a single pass over 25 games (`EVIDENCE_ARC.md` §0.4, §5.3). At Fable 5.1 list
prices that is on the order of hundreds of millions of tokens. The programme then needs that
substrate re-run under every baseline and every mechanism campaign at three seeds across three
or more families.

Two consequences, both of which the design must respect rather than hope about:

1. **The Max allowance is the budget, and it is not obviously large enough for a naive G3.**
   Before committing to a full 25-game reference run, measure cost on **three** games and
   extrapolate. `AGENT_CONSTITUTION.md` §6 carries this as an escalation trigger.
2. **The mechanism experiments must not require a frontier model in the inner loop.** The
   symbolic and procedural families (`PROPOSAL_v2.md` §6) are deliberately designed to run
   with small models or no model at all, which is what makes thousands of runs affordable. A
   mechanism that can only be evaluated inside a frontier-model harness cannot be evaluated at
   the scale this project needs. Design accordingly and say so in the mechanism card.

**Effort is the main lever** and is assigned by task type in `AGENT_CONSTITUTION.md` §8.
Mechanical work — log parsing, metric aggregation, artifact hashing, file bookkeeping — uses no
model at all.

---

## 11. Open items for bootstrap to close

Each is [VERIFY-ON-MACHINE]. Bootstrap records the observed value and the date here.

1. The accepted `--effort` value set, from `claude --help`.
   **Resolved 2026-09-04:** `claude --help` on Claude Code 2.1.260 prints
   `--effort <level>  Effort level for the current session (low, medium, high, xhigh, max)`.
   `ultracode` is **not** an accepted `--effort` value on this build; the section 2 row above
   that lists it is left as written and this line corrects it. Evidence: the ledger entry
   dated 2026-09-04 for task G0.1 (VERIFY-ON-MACHINE) in `state/LEDGER.jsonl`, which records
   the `claude --help | grep -A1 effort` output verbatim.
2. Whether the status line fires in headless `-p` and `state/usage.json` appears.
   **Resolved 2026-09-04:** No. Across 8 completed headless `-p` turns (`state/supervisor.jsonl`,
   event `turn`) `state/usage.json` never appeared, and every turn banner in
   `state/supervisor.out` reads `[gauge: none]` (6 of 6 banners). `.claude/hooks/statusline_probe.sh`
   is installed and `.claude/settings.json` points `statusLine` at it, so the hook is present and
   simply does not fire under `-p`. The backstop in section 7 carries the load. An interactive
   session was not tested and may still populate the file.
3. The exact rate-limit failure signature: exit code, stderr text, whether a reset timestamp
   is carried.
   **Not observable 2026-09-04:** no genuine usage-limit failure has occurred yet. The single
   `rate_limit` event in `state/supervisor.jsonl` (2026-09-04T06:08:38Z, `returncode 0`) was a
   false positive: the supervisor of that time matched the documented limit strings in the
   agent's own stdout at roughly 21% real usage, and the current `scripts/supervisor.py`
   classifies from stderr only (`RATE_LIMIT_PAT`). `state/tool_errors.jsonl` holds two entries,
   both `returncode 129` from signal 15, neither a limit. The first real limit will be logged
   verbatim there; resolve this item from that record.
4. Whether `CLAUDE_CODE_OAUTH_TOKEN` sustains a headless turn with no interactive login.
   **Resolved 2026-09-04:** Yes. `scripts/supervisor.py` prints a WARNING at start-up when
   `CLAUDE_CODE_OAUTH_TOKEN` is unset; `state/supervisor.out` carries no such warning across
   three supervisor starts, so the variable was set. From inside a headless turn's shell `env`
   shows no `CLAUDE_CODE_OAUTH_TOKEN` (it is stripped from child processes) and
   `claude auth status` reports `"loggedIn": false, "authMethod": "none"`, so no interactive
   login is stored for this user, yet 6 turns completed with `returncode 0`
   (`state/supervisor.jsonl`). The token alone sustains headless turns. Token lifetime has not
   yet been observed; the section 8 rows stand.
5. Whether a `PreToolUse` hook matching `Bash` reliably blocks `sed -i` and shell redirection
   against a protected path.
   **Resolved 2026-09-04:** Yes, for anything visible in the command string.
   `tests/integration/test_control_surface_hook.py` (SHA-256
   `bac67b22831eb32fa2731c23dc1612885f205e3ef65353ccb4b2378e1bc7d7a0`) feeds 29 synthetic
   payloads to `.claude/hooks/protect_control_surface.sh` exactly as Claude Code does: `sed -i`,
   `>`, `>>`, `tee -a`, `cp`, `git checkout --` and `python -c` against `preregistration/G0.yaml`,
   `scripts/supervisor.py` (relative and absolute path), `state/PINNED_HASHES.json`,
   `.claude/settings.json`, `AGENT_CONSTITUTION.md` and `PROPOSAL_v2.md` are all denied with
   exit 2 and `permissionDecision: deny`; reads, `sha256sum`, `pytest`, `git commit`, and writes
   to `/tmp` and to `docs/EVIDENCE_*.md` are allowed. Result: 29 passed. Observed live: a
   heredoc that merely named a frozen file was denied (ledger 2026-09-04T06:46:07Z), and
   `ls -la .claude/hooks 2>&1` was denied because `2>&1` matches the redirect pattern, so the
   hook errs over-inclusive, never under-inclusive. Known gap, pinned by the same test: a
   script invoked by name (`python scripts/x.py`) that writes to a frozen path is invisible to
   the hook; the supervisor's pinned-hash check (section 5, layer 2) is what holds against it.
6. Headless behaviour at context exhaustion.
   **Not observable 2026-09-04:** no headless turn has reached context exhaustion. The longest
   turn ran 500 s (`state/supervisor.jsonl`); the supervisor starts a fresh session per turn
   without `--continue`, so context stays flat by design and the condition may never arise.
   `claude --help` on 2.1.260 exposes `--autocompact <auto|tokens>` (auto, or 100k-1M tokens),
   which is the documented lever if it ever does.
7. Whether Fable 5.1 has a separate allowance from other models on this plan.
   **Not observable 2026-09-04:** the gauge never fires in headless mode (item 2), so no
   per-model `rate_limits` fields have been seen, and the CLI exposes no non-interactive usage
   query (`claude --help`, 2.1.260). Re-check if `state/usage.json` ever appears or from an
   interactive `/usage` view.
8. Installed Claude Code version, and whether it is native Windows or WSL.
   **Resolved 2026-09-04:** Claude Code 2.1.260 (`claude --version`), a native Linux install at
   `/home/afazeli2006/.local/bin/claude` linking to `~/.local/share/claude/versions/2.1.260`,
   running inside WSL2 (Ubuntu 24.04.4 LTS, kernel `6.18.33.2-microsoft-standard-WSL2` from
   `uname -a`); Python 3.12.3, uv 0.12.7. Not native Windows.
9. The headless CLI's failure shape when a call is made from inside a turn without a
   credential, and which flags 2.1.260 accepts for a tool-free single call.
   **Observed 2026-09-04 (G3.5 probe; ledger entry for task G3.5 dated 2026-09-04T20:58Z in
   `state/LEDGER.jsonl`):** `claude -p --output-format json --model claude-fable-5-1
   --effort low --tools "" --permission-prompts none --no-session-persistence`, prompt on
   stdin, cwd a temporary directory, environment minus `ARC_*`, `CLAUDECODE` and
   `CLAUDE_CODE_ENTRYPOINT`, exits **1** in 0.77 s with **nothing on stderr** and a JSON
   result object on stdout: `is_error: true`, `subtype: "success"` (not an error subtype),
   `terminal_reason: "api_error"`, `api_error_status: null`,
   `result: "Not logged in · Please run /login"`, `total_cost_usd: 0`, every `usage` count
   0, `modelUsage: {}`. Consequences: the error text lives in stdout's JSON `result`;
   `is_error` is the reliable flag and `subtype` is not; all six flags were accepted. The
   `usage` object also carries `cache_creation.ephemeral_1h_input_tokens` and
   `ephemeral_5m_input_tokens`, `service_tier`, `speed`, `iterations`,
   `server_tool_use` and `output_tokens_details.thinking_tokens`, so the adapter records
   `usage` verbatim and sums only the four documented keys (section 7). Source of the
   flags: `claude --help` on 2.1.260 and
   [code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless).
   **Extended 2026-09-04T21:27Z (G3.5 second half; ledger entries for task G3.5 dated
   2026-09-04 after 21:29Z in `state/LEDGER.jsonl`) — where the credential is dropped.**
   Environment key sets were compared by name only, through `/proc/<pid>/environ`
   ([proc_pid_environ(5)](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html));
   no value was read or printed. The supervisor process (`python3 scripts/supervisor.py`) and
   the turn's own `claude -p` process (2.1.260) both carry `CLAUDE_CODE_OAUTH_TOKEN`. The Bash
   tool's shell inside that turn carries every other key of the turn process, plus twelve
   session markers the CLI adds (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`,
   `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_EXECPATH`,
   `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_EFFORT`,
   `CLAUDE_PID`, `AI_AGENT`, `GIT_EDITOR`, `COREPACK_ENABLE_AUTO_PIN`), and lacks exactly one
   key: `CLAUDE_CODE_OAUTH_TOKEN`. So the CLI itself removes the credential from the
   environment of its tool subprocesses; `scripts/supervisor.py` (`env = dict(os.environ)`)
   and the adapter (which forwards the parent environment minus `ARC_*` and two markers) do
   not. Consequence: "forward the variable the turn already has" cannot authenticate a
   runner-spawned call, because the turn's shell never has it. The adapter now refuses such a
   call before any process starts (`CallRefused`, reason `authentication_unavailable`; the
   repeated probe at 21:27:28Z: exit_code -2, 0.0 s, no temporary directory created, no login
   attempted). Item 4 above stands; this extends it.
