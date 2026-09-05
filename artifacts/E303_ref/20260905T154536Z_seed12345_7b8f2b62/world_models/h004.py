# GOAL: the level is completed when the 13 mark of the horizontal 14-coloured bar reaches the hollow diamond centre (10,52) and the 13 mark of the vertical 11-coloured bar reaches the diamond centre (52,10); each "]" click extends the horizontal bar by 3 cells (mark x += 3), "[" retracts it by 3, "u" extends the vertical bar by 3 (mark y += 3) and "n" retracts it by 3, the mark always sitting one cell before the bar's end.
import copy

BAR_BUDGET = 50
STEP = 3
TARGET_A = 52   # x of mark for piece A (row 10)
TARGET_B = 52   # y of mark for piece B (col 10)
START_A = 31
START_B = 34
MIN_MARK = 28
MAX_MARK = 62

# button regions (y0, y1, x0, x1) inclusive
BTN_LEFT = (19, 23, 37, 41)
BTN_RIGHT = (19, 23, 43, 47)
BTN_UP = (36, 40, 22, 26)
BTN_DOWN = (42, 46, 22, 26)


def _in(region, act):
    if act is None or act.get("action") != 6:
        return False
    d = act.get("data") or {}
    if "x" not in d or "y" not in d:
        return False
    y0, y1, x0, x1 = region
    return y0 <= d["y"] <= y1 and x0 <= d["x"] <= x1


def _clamp(v):
    return max(MIN_MARK, min(MAX_MARK, v))


def _marks(actions):
    a, b = START_A, START_B
    for act in actions:
        if _in(BTN_LEFT, act):
            a = _clamp(a - STEP)
        elif _in(BTN_RIGHT, act):
            a = _clamp(a + STEP)
        elif _in(BTN_UP, act):
            b = _clamp(b - STEP)
        elif _in(BTN_DOWN, act):
            b = _clamp(b + STEP)
    return a, b


def predict(history, action):
    frame = copy.deepcopy(history[-1]["frame"])
    grid = frame[0]
    H, W = len(grid), len(grid[0])
    levels = history[-1]["levels_completed"]

    actions = [h["action"] for h in history[1:]] + [action]
    mark_a, mark_b = _marks(actions)

    # --- piece A (horizontal bar, rows 9-11) ---
    for y in (9, 10, 11):
        for x in range(28, W):
            grid[y][x] = 5
    # diamond A around (10,52)
    for (y, x) in ((9, 52), (11, 52), (10, 51), (10, 53)):
        grid[y][x] = 13
    for y in (9, 10, 11):
        grid[y][27] = 3
        for x in range(28, min(W, mark_a + 2)):
            grid[y][x] = 14
    grid[10][mark_a] = 13

    # --- piece B (vertical bar, cols 9-11) ---
    for y in range(28, H - 1):
        for x in (9, 10, 11):
            grid[y][x] = 5
    # diamond B around (52,10)
    for (y, x) in ((51, 10), (53, 10), (52, 9), (52, 11)):
        grid[y][x] = 13
    for x in (9, 10, 11):
        grid[27][x] = 3
        for y in range(28, min(H - 1, mark_b + 2)):
            grid[y][x] = 11
    grid[mark_b][10] = 13

    # --- bottom action bar: round(64*n/50) cells of 4 from the right ---
    n = len(history)
    filled = int(W * n / BAR_BUDGET + 0.5)
    filled = max(0, min(W, filled))
    for x in range(W):
        grid[H - 1][x] = 4 if x >= W - filled else 3

    state = "NOT_FINISHED"
    if mark_a == TARGET_A and mark_b == TARGET_B:
        levels += 1
        state = "NOT_FINISHED"

    return {
        "frame": frame,
        "state": state,
        "levels_completed": levels,
        "available_actions": [6],
    }
