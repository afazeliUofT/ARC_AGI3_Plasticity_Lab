# GOAL: the level is completed when the 13 mark of the horizontal 14-coloured bar sits on the hollow diamond centre (row 10, col 52) AND the 13 mark of the vertical 11-coloured bar sits on its diamond centre (row 52, col 10); the diamond cells stay 13 even when the bar passes over them, clicking the left/right half of the top button box retracts/extends the horizontal bar by 3 and clicking the upper/lower half of the side button box retracts/extends the vertical bar by 3 (the mark is always one cell before the bar's end).
import copy

BAR_BUDGET = 50
STEP = 3
TARGET = 52
START_END_A = 32   # last col of horizontal bar at reset (mark at 31)
START_END_B = 35   # last row of vertical bar at reset (mark at 34)
MIN_END = 29
MAX_END = 63

# button boxes (inclusive, borders count): (y0, y1, x0, x1, split)
HBOX = (18, 24, 36, 48, 42)   # split by column
VBOX = (35, 47, 21, 27, 41)   # split by row

H_DIAMOND = ((9, 52), (11, 52), (10, 51), (10, 53))
V_DIAMOND = ((51, 10), (53, 10), (52, 9), (52, 11))


def _click(act):
    if act is None or act.get("action") != 6:
        return None
    d = act.get("data") or {}
    if "x" not in d or "y" not in d:
        return None
    return d["x"], d["y"]


def _button(act):
    c = _click(act)
    if c is None:
        return None
    x, y = c
    y0, y1, x0, x1, split = HBOX
    if y0 <= y <= y1 and x0 <= x <= x1:
        if x < split:
            return "left"
        if x > split:
            return "right"
        return None
    y0, y1, x0, x1, split = VBOX
    if y0 <= y <= y1 and x0 <= x <= x1:
        if y < split:
            return "up"
        if y > split:
            return "down"
        return None
    return None


def _clamp(v):
    return max(MIN_END, min(MAX_END, v))


def _ends(actions):
    a, b = START_END_A, START_END_B
    for act in actions:
        btn = _button(act)
        if btn == "left":
            a = _clamp(a - STEP)
        elif btn == "right":
            a = _clamp(a + STEP)
        elif btn == "up":
            b = _clamp(b - STEP)
        elif btn == "down":
            b = _clamp(b + STEP)
    return a, b


def predict(history, action):
    frame = copy.deepcopy(history[-1]["frame"])
    grid = frame[0]
    H, W = len(grid), len(grid[0])
    levels = history[-1]["levels_completed"]

    actions = [h["action"] for h in history[1:]] + [action]
    end_a, end_b = _ends(actions)
    mark_a, mark_b = end_a - 1, end_b - 1

    # --- horizontal bar (rows 9-11, cols 28..W-1) ---
    for y in (9, 10, 11):
        for x in range(28, W):
            grid[y][x] = 5
        for x in range(28, min(W, end_a + 1)):
            grid[y][x] = 14
    grid[10][mark_a] = 13
    for (y, x) in H_DIAMOND:
        grid[y][x] = 13

    # --- vertical bar (cols 9-11, rows 28..H-2) ---
    for x in (9, 10, 11):
        for y in range(28, H - 1):
            grid[y][x] = 5
        for y in range(28, min(H - 1, end_b + 1)):
            grid[y][x] = 11
    grid[mark_b][10] = 13
    for (y, x) in V_DIAMOND:
        grid[y][x] = 13

    # --- bottom action counter: round(W*n/50) cells of 4 from the right ---
    n = len(history)
    filled = int(W * n / BAR_BUDGET + 0.5)
    filled = max(0, min(W, filled))
    for x in range(W):
        grid[H - 1][x] = 4 if x >= W - filled else 3

    state = "NOT_FINISHED"
    if mark_a == TARGET and mark_b == TARGET:
        levels += 1
        state = "NOT_FINISHED"

    return {
        "frame": frame,
        "state": state,
        "levels_completed": levels,
        "available_actions": [6],
    }
