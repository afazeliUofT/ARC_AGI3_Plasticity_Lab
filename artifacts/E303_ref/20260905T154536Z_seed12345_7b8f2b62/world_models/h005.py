# GOAL: the level is completed when the 13 mark of the horizontal 14-coloured bar reaches the hollow diamond centre (row 10, col 52) and the 13 mark of the vertical 11-coloured bar reaches the diamond centre (row 52, col 10); clicking the left half of the top button box retracts the horizontal bar by 3, its right half extends it by 3, clicking the upper half of the side button box retracts the vertical bar by 3 and its lower half extends it by 3 (the mark always sits one cell before the bar's end).
import copy

BAR_BUDGET = 50
STEP = 3
TARGET_A = 52   # x of mark for horizontal bar (row 10)
TARGET_B = 52   # y of mark for vertical bar (col 10)
START_A = 31
START_B = 34
MIN_MARK = 28
MAX_MARK = 62

# button boxes (inclusive): horizontal box rows 18-24, cols 36-48, split at col 42
# vertical box rows 35-47, cols 21-27, split at row 41
HBOX = (18, 24, 36, 48, 42)
VBOX = (35, 47, 21, 27, 41)


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
    return max(MIN_MARK, min(MAX_MARK, v))


def _marks(actions):
    a, b = START_A, START_B
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
    mark_a, mark_b = _marks(actions)

    # --- horizontal bar (rows 9-11) ---
    for y in (9, 10, 11):
        for x in range(28, W):
            grid[y][x] = 5
    for (y, x) in ((9, 52), (11, 52), (10, 51), (10, 53)):
        grid[y][x] = 13
    for y in (9, 10, 11):
        grid[y][27] = 3
        for x in range(28, min(W, mark_a + 2)):
            grid[y][x] = 14
    grid[10][mark_a] = 13

    # --- vertical bar (cols 9-11) ---
    for y in range(28, H - 1):
        for x in (9, 10, 11):
            grid[y][x] = 5
    for (y, x) in ((51, 10), (53, 10), (52, 9), (52, 11)):
        grid[y][x] = 13
    for x in (9, 10, 11):
        grid[27][x] = 3
        for y in range(28, min(H - 1, mark_b + 2)):
            grid[y][x] = 11
    grid[mark_b][10] = 13

    # --- bottom action counter: round(64*n/50) cells of 4 from the right ---
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
