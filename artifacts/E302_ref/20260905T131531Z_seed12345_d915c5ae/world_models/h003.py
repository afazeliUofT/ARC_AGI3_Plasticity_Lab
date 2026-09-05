# GOAL: the level is completed when the horizontal piece's 13 head reaches the diamond target centre at (row 10, col 52) and the vertical piece's 13 head reaches the diamond target centre at (row 52, col 10); each arrow-button click moves the corresponding head 3 cells.
import copy

BG = 5
BUDGET = 50
STEP = 3

H_ANCHOR = 27   # column of horizontal piece anchor (colour 3), rows 9-11
V_ANCHOR = 27   # row of vertical piece anchor (colour 3), cols 9-11
H_TARGET = 52
V_TARGET = 52
H_START = 31
V_START = 34


def _button(x, y):
    if 18 <= y <= 24 and 36 <= x <= 48:
        if x < 42:
            return "L"
        if x > 42:
            return "R"
        return None
    if 35 <= y <= 47 and 21 <= x <= 27:
        if y < 41:
            return "U"
        if y > 41:
            return "D"
        return None
    return None


def _apply(state, act):
    """state = (hx, vy, k). Returns new state."""
    hx, vy, k = state
    if act is None:
        return hx, vy, k
    a = act.get("action")
    if a == 0:
        return H_START, V_START, 0
    if a != 6:
        return hx, vy, k
    if k >= BUDGET:
        # game over: further clicks do nothing
        return hx, vy, k
    d = act.get("data") or {}
    k += 1
    if "x" not in d or "y" not in d:
        return hx, vy, k
    b = _button(int(d["x"]), int(d["y"]))
    if b == "L":
        hx = max(H_ANCHOR + 1, hx - STEP)
    elif b == "R":
        hx = min(62, hx + STEP)
    elif b == "U":
        vy = max(V_ANCHOR + 1, vy - STEP)
    elif b == "D":
        vy = min(62, vy + STEP)
    return hx, vy, k


def predict(history, action):
    frame = copy.deepcopy(history[0]["frame"])
    g = frame[0]

    st = (H_START, V_START, 0)
    for rec in history[1:]:
        st = _apply(st, rec.get("action"))
    st = _apply(st, action)
    hx, vy, k = st

    # clear original piece locations (keep anchors)
    for r in range(9, 12):
        for c in range(28, 33):
            g[r][c] = BG
    for r in range(28, 36):
        for c in range(9, 12):
            g[r][c] = BG

    # redraw diamond targets
    for (r, c) in [(9, 52), (10, 51), (10, 53), (11, 52),
                   (51, 10), (52, 9), (52, 11), (53, 10)]:
        g[r][c] = 13

    # horizontal piece: anchor at col 27, body cols 28..hx+1, head at (10,hx)
    for r in range(9, 12):
        g[r][H_ANCHOR] = 3
        for c in range(H_ANCHOR + 1, min(64, hx + 2)):
            g[r][c] = 14
    g[10][hx] = 13

    # vertical piece: anchor at row 27, body rows 28..vy+1, head at (vy,10)
    for c in range(9, 12):
        g[V_ANCHOR][c] = 3
        for r in range(V_ANCHOR + 1, min(63, vy + 2)):
            g[r][c] = 11
    g[vy][10] = 13

    # bottom bar fills with 4 from the right
    filled = int(64 * k / BUDGET + 0.5)
    filled = max(0, min(64, filled))
    for c in range(64):
        g[63][c] = 3
    for c in range(64 - filled, 64):
        g[63][c] = 4

    levels = history[-1]["levels_completed"]
    state = "NOT_FINISHED"
    if hx == H_TARGET and vy == V_TARGET:
        levels += 1
        state = "NOT_FINISHED"
    elif k >= BUDGET:
        state = "GAME_OVER"

    return {
        "frame": frame,
        "state": state,
        "levels_completed": levels,
        "available_actions": [6],
    }
