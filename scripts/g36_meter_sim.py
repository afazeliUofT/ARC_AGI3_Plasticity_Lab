"""Simulate the supervisor's five-hour meter under continued deferral turns.

Reads state/supervisor.jsonl turn records (ts, elapsed_s) since throttle
count_from, then replays the supervisor's rule: run a turn whenever
used < cap; when used >= cap sleep until the oldest turn ages out (+60 s).
A deferral turn costs the median observed deferral-turn elapsed time and
the gap between turns is the median observed gap. Reports the minimum
meter value reachable at any turn start over the next N hours.
"""
import json
import statistics
from datetime import datetime, timedelta, timezone

CAP = 5000
WINDOW = 5 * 3600
COUNT_FROM = 1788552824  # state/throttle.json

def parse(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()

rows = [json.loads(l) for l in open("state/supervisor.jsonl")]
turns = [(parse(r["ts"]), int(r["elapsed_s"])) for r in rows if r.get("event") == "turn"]
turns = [(ts, s) for ts, s in turns if ts >= COUNT_FROM]

# deferral turns: everything from 2026-09-04T22:05Z onward
defer_start = parse("2026-09-04T22:05:00Z")
deferrals = [(ts, s) for ts, s in turns if ts >= defer_start]
d_cost = statistics.median(s for _, s in deferrals)
gaps = [b[0] - a[0] for a, b in zip(deferrals, deferrals[1:]) if b[0] - a[0] < 600]
d_gap = statistics.median(gaps)
print(f"deferral turns so far: {len(deferrals)}, total metered {sum(s for _, s in deferrals)} s, "
      f"median cost {d_cost:.0f} s, median start-to-start gap {d_gap:.0f} s")

def used_at(t: float, hist: list[tuple[float, int]]) -> tuple[int, float]:
    inwin = [(ts, s) for ts, s in hist if ts >= t - WINDOW]
    return sum(s for _, s in inwin), (min(ts for ts, _ in inwin) if inwin else 0.0)

hist = list(turns)
# the turn record ts is the turn END; the meter at turn start uses records so far
t = turns[-1][0] + d_gap - turns[-1][1]  # next turn start
horizon = t + 8 * 3600
min_used, min_when = 10**9, None
starts = []
while t < horizon:
    used, oldest = used_at(t, hist)
    if used >= CAP:
        t = oldest + WINDOW + 60
        continue
    starts.append((t, used))
    if used < min_used:
        min_used, min_when = used, t
    hist.append((t + d_cost, int(d_cost)))  # record at turn end
    t = t + d_gap

iso = lambda x: datetime.fromtimestamp(x, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print(f"simulated turn starts in next 8 h: {len(starts)}")
print(f"minimum meter at any turn start: {min_used} s at {iso(min_when)}")
below = [(iso(a), b) for a, b in starts if b <= 3000]
print(f"turn starts with meter <= 3000 s: {len(below)}", below[:3])
# meter if turns stop now (blocked_on), i.e. pure age-out
for h in (1, 2, 3, 4, 5):
    u, _ = used_at(turns[-1][0] + h * 3600, turns)
    print(f"if no further turns run: meter {u} s at {iso(turns[-1][0] + h*3600)}")
