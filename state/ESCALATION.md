# ESCALATION - idle turns until the Friday reset would burn about 97 E303-sets of allowance

**Written:** 2026-09-05T23:59Z, HEAD dcf7e5a, task G3.6b (graded-set preparation complete, waiting for the reset)
**Constitution reason:** section 6 item 13 (the only clean fix is a scheduled hold in `scripts/supervisor.py`,
a frozen file, or an operator action on the supervisor process); item 10 in spirit (your directive of
2026-09-05T19:19:50Z reserves the weekly allowance for the graded set, and the idle loop would consume it).

**How to answer:** append a section to THIS file that begins with a line `## ANSWER`. Nothing else counts
(not a chat message, not an edit elsewhere). The supervisor checks this file every 10 minutes while
blocked and wakes as soon as the `## ANSWER` line exists. While blocked it runs no turns and spends no
model time, which is the point of this escalation: **blocking is the only zero-cost wait the agent has.**

## What is blocked

Nothing scientific. Steps 1-20 of G3.6b are done and committed (HEAD dcf7e5a): E304_ref config, G3b
pre-registration (sha256 99a01908), verifier overlay, queue / record / accounting scripts, recipe, digest.
Your directive forbids queueing any graded-set job before Friday 2026-09-11 17:00 local (America/Toronto).
`scripts/g3_next_job.py --dry-run` refuses correctly (exit 2, "before earliest_start_local"). There is
nothing left to build without spending model time on speculative engineering, which the same directive
also forbids.

## The finding of this turn: the idle wait is not free

The supervisor starts a new turn about a minute after the previous one ends, and it has no directive an
agent may set to make it wait for a date. So "idle until Friday" means one metered `claude -p` turn per
minute for 5.9 days. Measured from `state/supervisor.jsonl` (gitignored) over the seven idle turns run so
far (2026-09-05T23:50Z to 23:57Z):

```
idle turns so far: 7, metered 574 s, elapsed [229, 81, 37, 38, 67, 66, 56] s
median cost per idle turn (excluding the first): 61 s; median start-to-start gap: 66.5 s
hours to the reset (2026-09-11T21:00Z): 141.0
projected idle turns: ~7,600; projected metered model time: ~466,000 s (~129 h)
for scale: the whole three-run E303 set cost 4,785.7 s of model time -> the idle wait costs ~97 E303 sets
per five-hour window: ~16,500 s metered, UNDER the 20,000 s ceiling in state/throttle.json,
  so the self-throttle never sleeps and the burn is continuous
```

Every one of those turns is a real Claude Code invocation at effort high against your subscription's
seven-day window, the same window you said was 64 percent consumed at 13 percent elapsed. This is the
deferral livelock of 2026-09-05T02:04Z again in a new costume, and your answer then said plainly: "Do not
spend turns waiting ... again." So the agent stops here rather than repeat a documented failure.

## What I already tried

- Seven minimal idle turns (ledger decisions `waiting_for_reset` 2026-09-05T23:51:22Z to 23:56:09Z),
  each ~60 s; the sixth already flagged the cost for the next digest.
- Read the supervisor's scheduling (read-only): the only sleeps are the ceiling sleep with hysteresis,
  the usage-gauge sleep (gauge never fires headless), rate-limit sleeps, and the blocked-on-human sleep
  in 600 s steps. No wait-until directive exists (this was option B on 2026-09-05T02:04Z, declined
  because option A fixed the metering problem of that day; it does not cover a calendar wait).

## Options - pick one, or write your own

**A. Answer `resume` on or after Friday 2026-09-11 17:00 local.** No change anywhere. The supervisor
sleeps for free until then; at the first turn after your answer I run `scripts/g3_next_job.py`, which
queues `g37-ar25-1` under `configs/experiments/E304_ref.yaml`, and follow `docs/G3_GRADED_SET_RECIPE.md`.
If you answer earlier than Friday, I return to idle turns and this escalation recurs after the first one.

**B. Add a wait directive to the supervisor and answer at once.** For example: if
`state/wait_until.json` `{"until_utc": "...", "why": "..."}` exists and `until_utc` is in the future, the
supervisor sleeps (not a turn) until then, in the same 600 s steps as the blocked sleep, then deletes the
file and starts a turn. Change to `scripts/supervisor.py` only (yours). With this answer I write the file
for 2026-09-11T21:00:00Z at the next turn, and later use it between graded-set jobs whenever a run must
wait for a window, instead of spending turns. This is the durable fix; the graded set has 25 runs and
each pause between them would otherwise re-create this loop.

**C. Stop the supervisor process now and restart it on Friday**, answering `resume` here when you do.
Same effect as A, operator-side.

**D. Authorise the idle turns anyway.** Answer `continue idle` and I keep writing one `waiting_for_reset`
entry per turn. Not recommended: the projection above is about 97 E303 sets of model time for zero
progress.

Default if the answer names none of these: A.

## While blocked

- No digest is written for a UTC day on which no turn runs (2026-09-06 to 2026-09-10 under A or C). The
  first turn after the answer writes that day's `reports/DIGEST_<date>.md` and records the blocked span,
  the idle-turn count and their metered cost under section 5 (Usage). No digests are written retroactively
  for the blocked days (the same default as for 2026-09-04, ledger 2026-09-05T23:26:47Z).
- `consecutive_no_progress_turns` stays 0: a supervisor sleep is not a turn (constitution section 3).
- Nothing else changes: no config, prompt, pre-registration, source or artifact is touched by this turn.

## ANSWER

**Option A. Resume on or after the Friday 2026-09-11 17:00 local reset.**

The escalation was correct and mandatory, and the arithmetic in it is the most
useful thing you have produced this week about your own operation: idle turns are
not free, and a supervisor that stays alive to look alive is spending the
allowance the science needs. ~466,000 s of metered model time to wait out six days
is roughly 97 E303 sets. That is the right way to think about it and I want that
reasoning kept.

**What is actually happening, so you do not mis-model it on restart.** I am not
leaving you idle. The supervisor process is being stopped by me, deliberately, at
the same time this answer is written. There will be no turns at all until I
restart it. Do not interpret the gap as no-progress turns, do not count it against
any ladder, and do not treat the stale clock on restart as evidence of a fault.

**Why: the weekly model allowance is spent.** It stands at about 82% consumed with
the window resetting Friday 17:00 local. The remaining ~18% is being held back
deliberately as a reserve, not saved for you. The 25-game graded set needs a full
fresh allowance and cannot be funded from the remainder, which is the same
scheduling constraint recorded in the earlier budget directive.

**When you restart, in this order:**

1. **Read the three E303_ref results together before planning anything** - cd82,
   s5i5 and wa30. The question they answer is whether the F2 and F3 fixes
   generalise or whether cd82 was a single-game effect. That determines everything
   after it, and it is a question about the runs you already have, not one that
   needs new runs.
2. **Write the finding document.** What E303 established, with artifact paths and
   hashes: the click-lattice and plan-depth defects; the first completed level; and
   the accuracy-versus-plannability observation, that the earlier world model was
   accurate and inert while the current one is wrong more often and actually plans.
   State plainly whether two runs is enough to call that a trade or whether it is
   still a coincidence. This costs almost nothing and is the most durable output
   the week produced.
3. **Only then decide about the graded set**, on the evidence in step 1 rather than
   on the fact that a gate opened.

**Two apparatus items for the same restart, both cheap:**

- The wa30 run reported 10,947 s of wall-clock against a 10,800 s supervisor kill
  and a runner limit that was supposed to fire strictly first. It produced results
  and exited zero, so nothing was lost this time, but the ordering is not holding
  with the margin it was designed to have. Widen the gap and record why.
- Turns 11 to 16 of this burst were 37-81 s each with no commit. That is the
  cheap-no-op pattern again. It did not trigger the guard because the ledger grew,
  but a ledger line without a commit is not progress. Consider whether the
  no-progress predicate should require both.

Route unchanged. G3 stays open and in_progress. This is a scheduling decision, not
a route change and not a KILL.
