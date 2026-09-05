# GOAL: the level is completed when both movable pieces (the 14-colored bar with its 13 mark near row 10 and the 11-colored column with its 13 mark near column 10) have been placed so that their 13 marks sit at the centres of the two 13-diamond targets at (10,52) and (52,10); a click anywhere on a diamond target moves the matching piece there.
import copy

BAR_BUDGET = 50          # bottom row (64 cells) depletes right-to-left over 50 actions
TARGET_A = (10, 52)      # diamond centre for the 14-piece (y, x)
TARGET_B = (52, 10)      # diamond centre for the 11-piece (y, x)
START_A = (10, 31)       # initial mark position of the 14-piece
START_B = (34, 10)       # initial mark position of the 11-piece

# templates: {(dy, dx): colour} relative to the 13 mark
TEMPLATE_A = {}
for dy in (-1, 0, 1):
    TEMPLATE_A[(dy, -4)] = 3
    for dx in range(-3, 2):
        TEMPLATE_A[(dy, dx)] = 14
TEMPLATE_A[(0, 0)] = 13

TEMPLATE_B = {}
for dx in (-1, 0, 1):
    TEMPLATE_B[(-7, dx)] = 3
    for dy in range(-6, 1):
        TEMPLATE_B[(dy, dx)] = 11
TEMPLATE_B[(0, 0)] = 13


def _hits(target, act):
    if act is None or act.get("action") != 6:
        return False
    d = act.get("data") or {}
    if "x" not in d or "y" not in d:
        return False
    ty, tx = target
    return abs(d["y"] - ty) <= 1 and abs(d["x"] - tx) <= 1


def _placed_flags(actions):
    a = b = False
    for act in actions:
        if _hits(TARGET_A, act):
            a = True
        if _hits(TARGET_B, act):
            b = True
    return a, b


def _erase(grid, template, mark):
    my, mx = mark
    for (dy, dx) in template:
        y, x = my + dy, mx + dx
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
            grid[y][x] = 5


def _draw(grid, template, mark):
    my, mx = mark
    for (dy, dx), c in template.items():
        y, x = my + dy, mx + dx
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
            grid[y][x] = c


def predict(history, action):
    last = history[-1]
    frame = copy.deepcopy(last["frame"])
    grid = frame[0]
    levels = last["levels_completed"]

    prev_actions = [h["action"] for h in history[1:]]
    a_before, b_before = _placed_flags(prev_actions)
    a_after, b_after = _placed_flags(prev_actions + [action])

    if a_after and not a_before:
        _erase(grid, TEMPLATE_A, START_A)
        _draw(grid, TEMPLATE_A, TARGET_A)
    if b_after and not b_before:
        _erase(grid, TEMPLATE_B, START_B)
        _draw(grid, TEMPLATE_B, TARGET_B)

    # bottom action bar: 64 cells, depleting from the right
    n = len(history)  # index of this action (1-based)
    remaining = max(0, BAR_BUDGET - n)
    filled = 64 - int(round(64.0 * remaining / BAR_BUDGET))
    filled = max(0, min(64, filled))
    width = len(grid[-1])
    for x in range(width):
        grid[-1][x] = 4 if x >= width - filled else 3

    state = "NOT_FINISHED"
    if a_after and b_after and not (a_before and b_before):
        levels += 1
        state = "NOT_FINISHED"

    return {
        "frame": frame,
        "state": state,
        "levels_completed": levels,
        "available_actions": [6],
    }
