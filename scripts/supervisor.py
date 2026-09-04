#!/usr/bin/env python3
"""
ARC-AGI-3 Plasticity Lab - autonomous supervisor.

This is the only process that runs forever, and it deliberately contains no model.
The thing that decides whether to keep going must not be the thing that can
hallucinate progress.

Each iteration it:
  1. verifies the control surface has not been altered (pinned hashes)
  2. reads state, budget and the usage gauge
  3. decides whether to run, pause for a usage window, or stop
  4. invokes Claude Code headless for one turn
  5. classifies the outcome, and checks that the ledger actually grew and a
     commit actually landed
  6. records everything and enforces the escalation ladder

Design notes that matter, all traceable to docs/EVIDENCE_TOOLING.md:

  * `--bare` is never used: it requires an API key and disables hooks, skills
    and CLAUDE.md, all of which this design needs.
  * Continuation is done here, not in a Stop hook. Whether a Stop hook can force
    the model to keep working is UNCONFIRMED, so the loop does not depend on it.
  * The usage gauge (state/usage.json, written by the statusline hook) is best
    effort - it is documented for interactive sessions and UNCONFIRMED for
    headless. The guaranteed path is classifying the rate-limit error and
    sleeping until the window resets. Both are implemented; neither is required.
  * A supervisor sleep is NOT a turn and never touches the no-progress counter.

Usage:
    python3 scripts/supervisor.py                # run
    python3 scripts/supervisor.py --dry-run      # decide, print, change nothing
    python3 scripts/supervisor.py --once         # exactly one turn
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
PROJECT_STATE = STATE / "PROJECT_STATE.json"
LEDGER = STATE / "LEDGER.jsonl"
BUDGET = STATE / "BUDGET.json"
PINNED = STATE / "PINNED_HASHES.json"
USAGE = STATE / "usage.json"
ESCALATION = STATE / "ESCALATION.md"
TOOL_ERRORS = STATE / "tool_errors.jsonl"
SUPERVISOR_LOG = STATE / "supervisor.jsonl"

MODEL = os.environ.get("ARC_LAB_MODEL", "claude-fable-5-1")

# Paths whose contents must not change while the programme runs.
# AGENT_CONSTITUTION.md section 7, control C2, layer 2. This check does not rely
# on the PreToolUse hook, which lives inside the project and is itself protected.
CONTROL_SURFACE = [
    "scripts/supervisor.py",
    "AGENT_CONSTITUTION.md",
    "PROPOSAL_v2.md",
    ".claude/settings.json",
    ".claude/hooks/protect_control_surface.sh",
]

TURN_PROMPT = """Continue the ARC-AGI-3 Plasticity Lab programme.

Follow AGENT_CONSTITUTION.md section 3, the turn protocol, exactly and in order:
orient from state/PROJECT_STATE.json and the ledger tail, verify the repository
agrees with the state, recall prior attempts at this task from state/LEDGER.jsonl,
do exactly ONE verifiable advancing step, verify it, record it in the ledger and
the state file, commit, and write a concrete next_action.

Do not do more than one step. Do not summarise the plan back to me. Do not ask a
question when a safe default exists - state the default in the ledger and proceed.

If you are blocked on one of the thirteen reasons in section 6, write
state/ESCALATION.md, set blocked_on, and stop cleanly."""

# Effort by task class. AGENT_CONSTITUTION.md section 8: mechanical work uses no
# model at all, so it never reaches this table.
EFFORT_BY_GATE_STATUS = {
    "awaiting_verdict": "max",   # referee
    "not_started": "max",        # planning and pre-registration
    "in_progress": "high",       # implementation and debugging
    "failed": "high",
}

# These are applied ONLY to the error channel, never to the agent's own output.
# The evidence base documents these very strings, so matching them in stdout
# classified a successful turn as a rate limit.
RATE_LIMIT_PAT = re.compile(
    r"(you'?ve hit your (session|weekly|usage) limit"
    r"|usage limit reached"
    r"|\brate_limit_error\b"
    r"|\b429\b[^0-9]{0,40}(too many|rate)"
    r"|(too many requests)[^0-9]{0,40}\b429\b)", re.I)
AUTH_PAT = re.compile(
    r"(login expired"
    r"|please run /login"
    r"|profile login expired"
    r"|\bauthentication_error\b"
    r"|invalid[ _]api[ _]key"
    r"|\b401\b[^0-9]{0,40}unauthor)", re.I)
TRANSIENT_PAT = re.compile(
    r"(\b(500|502|503|504|529)\b[^0-9]{0,40}(error|overload|unavailable|gateway|timeout)"
    r"|overloaded_error"
    r"|api_error"
    r"|connection (reset|refused|aborted)"
    r"|temporarily unavailable"
    r"|read timed out)", re.I)

FIVE_HOURS = 5 * 3600
SEVEN_DAYS = 7 * 24 * 3600

_stop_requested = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _stop_requested
    _stop_requested = True
    print(f"\n[supervisor] signal {signum} received; finishing the current turn then stopping.")


# ------------------------------------------------------------------ helpers --

def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        print(f"[supervisor] {path.name} is not valid JSON: {e}")
        return default


def write_json(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def head_commit() -> str:
    rc, out = git("rev-parse", "HEAD")
    return out if rc == 0 else ""


def ledger_len() -> int:
    try:
        return sum(1 for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip())
    except FileNotFoundError:
        return 0


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for p in (Path.home() / ".local/bin/claude",
              Path.home() / ".claude/local/claude",
              Path("/usr/local/bin/claude")):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


# --------------------------------------------------------------- decisions --

@dataclass
class Outcome:
    kind: str                       # ok | rate_limit | auth | transient | unknown
    returncode: int
    stdout: str = ""
    stderr: str = ""
    resets_at: int | None = None
    window: str | None = None       # five_hour | seven_day
    detail: str = ""


@dataclass
class Gauge:
    five_hour_pct: float | None = None
    five_hour_reset: int | None = None
    seven_day_pct: float | None = None
    seven_day_reset: int | None = None
    present: bool = False

    @classmethod
    def load(cls) -> "Gauge":
        d = read_json(USAGE, None)
        if not isinstance(d, dict):
            return cls()
        g = cls(present=True)
        fh, sd = d.get("five_hour") or {}, d.get("seven_day") or {}
        g.five_hour_pct = fh.get("used_percentage")
        g.five_hour_reset = fh.get("resets_at")
        g.seven_day_pct = sd.get("used_percentage")
        g.seven_day_reset = sd.get("resets_at")
        return g

    def over(self, threshold: float) -> tuple[bool, str | None, int | None]:
        for name, pct, reset in (("five_hour", self.five_hour_pct, self.five_hour_reset),
                                 ("seven_day", self.seven_day_pct, self.seven_day_reset)):
            if pct is not None and pct >= threshold:
                return True, name, reset
        return False, None, None


class Supervisor:
    def __init__(self, dry_run: bool = False, once: bool = False,
                 usage_stop_pct: float = 90.0) -> None:
        self.dry_run = dry_run
        self.once = once
        self.usage_stop_pct = usage_stop_pct
        self.claude = find_claude()
        self.backoff = 900          # 15 minutes, the floor for an unknown window
        self.turns_this_run = 0

    # -- control surface ----------------------------------------------------
    def check_control_surface(self) -> tuple[bool, str]:
        """Layer 2 of AGENT_CONSTITUTION section 7. Independent of any in-session hook."""
        pinned = read_json(PINNED, None)
        current = {p: sha256(ROOT / p) for p in CONTROL_SURFACE if (ROOT / p).exists()}
        if pinned is None:
            write_json(PINNED, {"pinned_utc": iso(), "hashes": current})
            return True, f"pinned {len(current)} control-surface files on first run"
        changed = [p for p, h in pinned.get("hashes", {}).items()
                   if p in current and current[p] != h]
        if changed:
            return False, ("control surface changed since it was pinned: "
                           + ", ".join(changed)
                           + ". Refusing to run. If this was you, delete "
                             "state/PINNED_HASHES.json to re-pin; if it was the agent, "
                             "that is a constitution section 6 item 13 violation.")
        added = {p: h for p, h in current.items() if p not in pinned.get("hashes", {})}
        if added:
            pinned["hashes"].update(added)
            write_json(PINNED, pinned)
            return True, f"pinned {len(added)} newly present control-surface files"
        return True, "control surface intact"


    def check_evidence_append_only(self) -> tuple[bool, str]:
        """Evidence documents may GROW - constitution section 6 item 13 allows
        append-only additions carrying a URL and a date - but must never shrink.
        Byte size is a crude proxy and a sufficient one: it cannot be gamed
        downward, which is the direction that matters."""
        pinned = read_json(PINNED, {}) or {}
        recorded = pinned.get("evidence_sizes") or {}
        docs = ROOT / "docs"
        current = {f.name: f.stat().st_size for f in sorted(docs.glob("EVIDENCE_*.md"))} \
            if docs.is_dir() else {}
        shrunk = [n for n, sz in current.items() if n in recorded and sz < recorded[n]]
        if shrunk:
            detail = ", ".join(f"{n} {recorded[n]}->{current[n]} bytes" for n in shrunk)
            return False, ("evidence document shrank, which section 6 item 13 forbids: "
                           + detail + ". Inspect the diff before continuing; delete "
                           "state/PINNED_HASHES.json only if the reduction was yours.")
        if current != recorded:
            pinned["evidence_sizes"] = current
            write_json(PINNED, pinned)
        return True, "evidence append-only ok"

    # -- gating -------------------------------------------------------------
    def blocked_on_human(self, st: dict[str, Any]) -> tuple[bool, str]:
        if not st.get("blocked_on"):
            return False, ""
        text = ESCALATION.read_text(encoding="utf-8") if ESCALATION.exists() else ""
        if re.search(r"^##\s*ANSWER", text, re.M):
            stamp = now().strftime("%Y%m%dT%H%M%SZ")
            (STATE / "escalations").mkdir(parents=True, exist_ok=True)
            ESCALATION.replace(STATE / "escalations" / f"{stamp}.md")
            ESCALATION.write_text("", encoding="utf-8")
            st["blocked_on"] = None
            write_json(PROJECT_STATE, st)
            append_jsonl(LEDGER, {
                "ts": iso(), "gate": st.get("current_gate", "?"),
                "task": (st.get("active_task") or {}).get("id", "?"),
                "event": "decision",
                "summary": "Human answered the escalation; block cleared by the supervisor.",
                "evidence": [f"state/escalations/{stamp}.md"]})
            return False, "escalation answered; resuming"
        return True, str(st["blocked_on"])

    def budget_breach(self, bud: dict[str, Any]) -> str | None:
        if bud.get("turns_used", 0) >= bud.get("max_turns_total", 10**9):
            return "max_turns_total reached (constitution section 6 item 10)"
        end = bud.get("programme_end_date")
        if end:
            try:
                if now().date() > datetime.fromisoformat(end).date():
                    return f"programme_end_date {end} has passed (section 6 item 10)"
            except ValueError:
                pass
        return None

    # -- the turn -----------------------------------------------------------
    def effort_for(self, st: dict[str, Any], bud: dict[str, Any]) -> str:
        policy = bud.get("effort_policy") or {}
        base = EFFORT_BY_GATE_STATUS.get(str(st.get("gate_status")), "high")
        if st.get("gate_status") == "awaiting_verdict":
            return str(policy.get("verdict", base))
        if st.get("gate_status") == "not_started":
            return str(policy.get("planning", base))
        return str(policy.get("implementation", base))

    def run_turn(self, effort: str) -> Outcome:
        assert self.claude
        cmd = [self.claude, "-p", TURN_PROMPT,
               "--model", MODEL,
               "--effort", effort,
               "--permission-mode", "acceptEdits",
               "--permission-prompts", "none",
               "--add-dir", str(Path.home()),
               "--add-dir", "/usr",
               "--output-format", "json"]
        # Deliberately NO --continue: state lives on disk, the conversation is
        # disposable, a fresh session re-reads settings, and context stays flat.

        env = dict(os.environ)
        env.setdefault("CLAUDE_PROJECT_DIR", str(ROOT))

        try:
            # start_new_session detaches the child into its own session, so a
            # SIGHUP aimed at the launching terminal cannot reach it. Without
            # this, closing the window killed turns mid-flight with rc 129:
            # nohup protects the supervisor, not the process it spawns.
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               timeout=3 * 3600, env=env, start_new_session=True)
        except subprocess.TimeoutExpired:
            return Outcome("transient", 124, detail="turn exceeded the 3 hour ceiling")

        out, err = r.stdout or "", r.stderr or ""

        # Prefer the structured signal. --output-format json emits one JSON
        # object; is_error distinguishes a failed turn from a successful one
        # whose text happens to mention failure.
        payload = None
        try:
            lines = [ln for ln in out.strip().splitlines() if ln.strip().startswith("{")]
            if lines:
                payload = json.loads(lines[-1])
        except Exception:
            payload = None
        is_err = bool(payload.get("is_error")) if isinstance(payload, dict) else False

        if r.returncode == 0 and not is_err:
            return Outcome("ok", 0, out, err)

        append_jsonl(TOOL_ERRORS, {
            "ts": iso(), "returncode": r.returncode, "is_error": is_err,
            "stderr": err[-4000:], "stdout_tail": out[-2000:]})

        # Classify from the ERROR CHANNEL ONLY. The agent's own prose lives in
        # stdout and documents these very strings; matching it there is what
        # produced a false rate limit at 21% real usage.
        text = err
        if isinstance(payload, dict) and is_err:
            text += "\n" + str(payload.get("result") or payload.get("error") or "")

        if RATE_LIMIT_PAT.search(text):
            window = "seven_day" if re.search(r"week", text, re.I) else "five_hour"
            m = re.search(r"resets?[_ ]?at\D{0,10}(\d{10})", text)
            return Outcome("rate_limit", r.returncode, out, err,
                           resets_at=int(m.group(1)) if m else None, window=window)
        if AUTH_PAT.search(text):
            return Outcome("auth", r.returncode, out, err)
        if TRANSIENT_PAT.search(text):
            return Outcome("transient", r.returncode, out, err)
        return Outcome("unknown", r.returncode, out, err)

    # -- sleeping -----------------------------------------------------------
    def sleep_until(self, target_epoch: int | None, window: str | None, why: str) -> None:
        """A supervisor sleep is not a turn. It never touches the no-progress counter."""
        if target_epoch:
            seconds = max(60, int(target_epoch - time.time()) + 30)
        else:
            ceiling = SEVEN_DAYS if window == "seven_day" else FIVE_HOURS
            seconds = min(self.backoff, ceiling)
            self.backoff = min(self.backoff * 2, ceiling)
        seconds = int(seconds * (1.0 + random.uniform(0, 0.05)))
        wake = now() + timedelta(seconds=seconds)
        self.log("sleep", why=why, window=window, seconds=seconds, wake_utc=iso(wake))
        print(f"[supervisor] {why}. Sleeping {seconds//60} min, waking {iso(wake)}.")
        if self.dry_run:
            return
        deadline = time.time() + seconds
        while time.time() < deadline and not _stop_requested:
            time.sleep(min(60, max(1, deadline - time.time())))
            # A human answer clears a block without waiting out the full sleep.
            if ESCALATION.exists() and re.search(r"^##\s*ANSWER",
                                                 ESCALATION.read_text(encoding="utf-8"), re.M):
                print("[supervisor] escalation answered during sleep; waking early.")
                return

    def log(self, event: str, **kw: Any) -> None:
        append_jsonl(SUPERVISOR_LOG, {"ts": iso(), "event": event, **kw})

    # -- main ---------------------------------------------------------------
    def loop(self) -> int:
        if not self.claude:
            print("[supervisor] FATAL: 'claude' not found on PATH.")
            return 2
        if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            print("[supervisor] WARNING: CLAUDE_CODE_OAUTH_TOKEN is not set. An interactive\n"
                  "             login expires after a few days and will kill a long run.\n"
                  "             Run 'claude setup-token' and export it. Continuing anyway.")

        print(f"[supervisor] claude={self.claude} model={MODEL} root={ROOT}")
        self.log("start", claude=self.claude, model=MODEL, dry_run=self.dry_run)

        while not _stop_requested:
            okc, msg = self.check_control_surface()
            if not okc:
                print(f"[supervisor] HALT: {msg}")
                self.log("halt", reason=msg)
                return 3

            oke, emsg = self.check_evidence_append_only()
            if not oke:
                print(f"[supervisor] HALT: {emsg}")
                self.log("halt", reason=emsg)
                return 8

            st = read_json(PROJECT_STATE, None)
            bud = read_json(BUDGET, {}) or {}
            if st is None:
                print("[supervisor] HALT: state/PROJECT_STATE.json missing or invalid.")
                return 4

            blocked, why = self.blocked_on_human(st)
            if blocked:
                print(f"[supervisor] blocked on a human: {why}")
                print(f"[supervisor] answer by appending a '## ANSWER' section to {ESCALATION}")
                self.log("blocked", reason=why)
                if self.once or self.dry_run:
                    return 0
                self.sleep_until(int(time.time()) + 600, None, "waiting for a human answer")
                continue

            breach = self.budget_breach(bud)
            if breach:
                print(f"[supervisor] HALT: {breach}")
                self.log("halt", reason=breach)
                return 5

            gauge = Gauge.load()
            over, window, reset = gauge.over(self.usage_stop_pct)
            if over:
                self.sleep_until(reset, window,
                                 f"usage gauge reports {window} at or above "
                                 f"{self.usage_stop_pct:.0f}%")
                continue

            effort = self.effort_for(st, bud)
            gate = st.get("current_gate", "?")
            print(f"[supervisor] turn {self.turns_this_run + 1}  gate={gate} "
                  f"status={st.get('gate_status')} effort={effort}"
                  + ("  [gauge: none]" if not gauge.present else
                     f"  [5h {gauge.five_hour_pct}% 7d {gauge.seven_day_pct}%]"))

            if self.dry_run:
                print("[supervisor] --dry-run: would invoke Claude Code now. Stopping.")
                return 0

            before_ledger, before_commit = ledger_len(), head_commit()
            t0 = time.time()
            out = self.run_turn(effort)
            elapsed = int(time.time() - t0)

            if out.kind == "rate_limit":
                self.log("rate_limit", window=out.window, returncode=out.returncode)
                self.sleep_until(out.resets_at, out.window,
                                 f"{out.window or 'usage'} limit hit")
                continue
            if out.kind == "auth":
                print("[supervisor] HALT: authentication failed or expired.\n"
                      "             Run 'claude setup-token' and export CLAUDE_CODE_OAUTH_TOKEN.\n"
                      "             (constitution section 6 item 1)")
                self.log("halt", reason="auth")
                return 6
            if out.kind == "transient":
                self.log("transient", returncode=out.returncode, detail=out.detail)
                self.sleep_until(None, "five_hour", "transient service error")
                continue

            self.backoff = 900
            self.turns_this_run += 1

            # Did anything actually happen? A turn that produced only prose made no progress.
            grew = ledger_len() > before_ledger
            committed = head_commit() != before_commit
            # A commit IS progress, with or without a ledger entry. Requiring
            # both meant an interrupted turn that had already committed real
            # work counted as thrashing, and three of those dispatch a
            # retrospective while five halt the run.
            progressed = grew or committed
            if committed and not grew:
                self.log("ledger_missing",
                         note="turn committed but appended no ledger entry")

            st = read_json(PROJECT_STATE, st) or st
            if progressed:
                st["consecutive_no_progress_turns"] = 0
            else:
                st["consecutive_no_progress_turns"] = int(
                    st.get("consecutive_no_progress_turns", 0)) + 1
            bud["turns_used"] = int(bud.get("turns_used", 0)) + 1
            bud["turns_this_gate"] = int(bud.get("turns_this_gate", 0)) + 1
            write_json(PROJECT_STATE, st)
            write_json(BUDGET, bud)

            npt = st["consecutive_no_progress_turns"]
            self.log("turn", kind=out.kind, returncode=out.returncode, elapsed_s=elapsed,
                     ledger_grew=grew, committed=committed, no_progress=npt, effort=effort)
            print(f"[supervisor] turn done in {elapsed}s  ledger+{int(grew)} "
                  f"commit={'yes' if committed else 'no'}  no_progress={npt}")

            if npt == 3:
                print("[supervisor] three no-progress turns: the next turn must run the "
                      "retrospective agent (constitution section 5, L4).")
                append_jsonl(LEDGER, {
                    "ts": iso(), "gate": gate, "task": "supervisor",
                    "event": "escalation", "escalation_level": 4,
                    "summary": "Three consecutive turns produced no ledger entry and no commit. "
                               "Dispatch the retrospective agent before continuing."})
            if npt >= 5:
                print("[supervisor] HALT: five no-progress turns (section 6 item 8).")
                if not ESCALATION.read_text(encoding="utf-8").strip():
                    ESCALATION.write_text(
                        "# Escalation: five consecutive no-progress turns\n\n"
                        f"Gate: {gate}\nTime: {iso()}\n\n"
                        "The agent ran five turns without appending to the ledger or landing a "
                        "commit. Something is stuck in a way the escalation ladder did not "
                        "resolve.\n\n"
                        "Look at `state/supervisor.jsonl` and the tail of `state/LEDGER.jsonl`, "
                        "then reply below.\n\n"
                        "Answer by appending a section that starts with `## ANSWER`.\n",
                        encoding="utf-8")
                st["blocked_on"] = "five consecutive no-progress turns"
                write_json(PROJECT_STATE, st)
                self.log("halt", reason="no_progress_5")
                return 7

            if self.once:
                return 0

            time.sleep(5)

        print("[supervisor] stopped cleanly.")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Autonomous supervisor for the ARC plasticity lab.")
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and print, but never invoke the model or change state")
    ap.add_argument("--once", action="store_true", help="run exactly one turn then exit")
    ap.add_argument("--usage-stop-pct", type=float, default=90.0,
                    help="pause when the usage gauge reaches this percent (default 90)")
    a = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    STATE.mkdir(parents=True, exist_ok=True)
    for p in (LEDGER, ESCALATION):
        p.touch(exist_ok=True)

    return Supervisor(dry_run=a.dry_run, once=a.once, usage_stop_pct=a.usage_stop_pct).loop()


if __name__ == "__main__":
    sys.exit(main())
