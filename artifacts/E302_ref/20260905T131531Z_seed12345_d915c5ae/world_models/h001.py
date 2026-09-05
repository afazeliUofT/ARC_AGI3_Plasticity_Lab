# GOAL: the level is completed when the 14-coloured piece's 13 dot reaches (row 10, col 52) and the 11-coloured piece's 13 dot reaches (row 52, col 10), i.e. both pieces are centred on their diamond target markers.
import copy

BG = 5
BUDGET = 50  # bar fills 64 cells over 50 clicks: filled = round(64*k/50)


def _button(x, y):
    # top box rows 18-24, cols 36-48: left/right control for horizontal piece
    if 18 <= y <= 24 and 36 <= x <= 48:
        if x < 42:
            return "L"
        if x > 42:
            return "R"
        return None
    # bottom box rows 35-47, cols 21-27: up/down control for vertical piece
    if 35 <= y <= 47 and 21 <= x <= 27:
        if y < 41:
            return "U"
        if y > 41:
            return "D"
        return None
    return None


def _apply(ax, by, act):
    if act is None or act.get("action") != 6:
        return ax, by
    d = act.get("data") or {}
    if "x" not in d or "y" not in d:
        return ax, by
    b = _button(int(d["x"]), int(d["y"]))
    if b == "L" and ax - 1 >= 4:
        ax -= 1
    elif b == "R" and ax + 1 <= 62:
        ax += 1
    elif b == "U" and by - 1 >= 7:
        by -= 1
    elif b == "D" and by + 1 <= 62:
        by += 1
    return ax, by


def predict(history, action):
    base = history[0]["frame"]
    frame = copy.deepcopy(base)
    g = frame[0]

    # replay all actions to get piece positions and click count
    ax, by = 31, 34
    k = 0
    for rec in history[1:]:
        ax, by = _apply(ax, by, rec.get("action"))
        k += 1
    ax, by = _apply(ax, by, action)
    k += 1

    # clear original piece locations
    for r in range(9, 12):
        for c in range(27, 33):
            g[r][c] = BG
    for r in range(27, 36):
        for c in range(9, 12):
            g[r][c] = BG

    # diamond targets (already in base, redraw for safety)
    for (r, c) in [(9, 52), (10, 51), (10, 53), (11, 52), (51, 10), (52, 9), (52, 11), (53, 10)]:
        g[r][c] = 13

    # horizontal piece (colour 14, tail 3 on the left, dot at col ax on row 10)
    for r in range(9, 12):
        g[r][ax - 4] = 3
        for c in range(ax - 3, ax + 2):
            g[r][c] = 14
    g[10][ax] = 13

    # vertical piece (colour 11, tail 3 on top, dot at row by on col 10)
    for c in range(9, 12):
        g[by - 7][c] = 3
        for r in range(by - 6, by + 2):
            g[r][c] = 11
    g[by][10] = 13

    # bottom bar: fills with 4 from the right
    filled = int(64 * k / BUDGET + 0.5)
    filled = max(0, min(64, filled))
    for c in range(64):
        g[63][c] = 3
    for c in range(64 - filled, 64):
        g[63][c] = 4

    levels = history[-1]["levels_completed"]
    state = "NOT_FINISHED"
    if ax == 52 and by == 52:
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
