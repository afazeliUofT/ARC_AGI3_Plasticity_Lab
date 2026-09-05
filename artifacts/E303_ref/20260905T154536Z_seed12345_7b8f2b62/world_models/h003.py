# GOAL: the level is completed when the 13 mark of the 14-coloured bar sits in the hollow diamond centre (10,52) and the 13 mark of the 11-coloured column sits in the hollow diamond centre (52,10); the "[" / "]" buttons in the upper control box move the bar one cell left/right per click and the "n" / "u" buttons in the lower box move the column one cell up/down per click.
import copy

BAR_BUDGET = 50
TARGET_A = (10, 52)
TARGET_B = (52, 10)
START_A = (10, 31)
START_B = (34, 10)

# button regions (y0, y1, x0, x1) inclusive, interior of the control boxes
BTN_LEFT = (19, 23, 37, 41)
BTN_RIGHT = (19, 23, 43, 47)
BTN_UP = (36, 40, 22, 26)
BTN_DOWN = (42, 46, 22, 26)

TEMPLATE_A = {}
for dy in (-1, 0, 1):
    TEMPLATE_A[(dy, -4)] = 3
    for dx in range(-3, 2):
        TEMPLATE_A[(dy, dx)] = 14
TEMPLATE_A[(0, 0)] = 13

TEMPLATE_B = {}
for dx in (-1, 0, 1):
    TEMPLATE_B[(-7, dx)] = 3
    for dy in range(-6, 2):
        TEMPLATE_B[(dy, dx)] = 11
TEMPLATE_B[(0, 0)] = 13


def _in(region, act):
    if act is None or act.get("action") != 6:
        return False
    d = act.get("data") or {}
    if "x" not in d or "y" not in d:
        return False
    y0, y1, x0, x1 = region
    return y0 <= d["y"] <= y1 and x0 <= d["x"] <= x1


def _offsets(actions):
    dx = dy = 0
    for act in actions:
        if _in(BTN_LEFT, act):
            dx -= 1
        elif _in(BTN_RIGHT, act):
            dx += 1
        elif _in(BTN_UP, act):
            dy -= 1
        elif _in(BTN_DOWN, act):
            dy += 1
    return dx, dy


def _draw(grid, template, mark):
    my, mx = mark
    H, W = len(grid), len(grid[0])
    for (dy, dx), c in template.items():
        y, x = my + dy, mx + dx
        if 0 <= y < H and 0 <= x < W:
            grid[y][x] = c


def _diamond(grid, centre):
    # hollow ring: centre stays background
    cy, cx = centre
    H, W = len(grid), len(grid[0])
    for (y, x) in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
        if 0 <= y < H and 0 <= x < W:
            grid[y][x] = 13


def predict(history, action):
    base = copy.deepcopy(history[0]["frame"])
    grid = base[0]
    levels = history[-1]["levels_completed"]
    H, W = len(grid), len(grid[0])

    # erase pieces from their initial positions
    for tmpl, start in ((TEMPLATE_A, START_A), (TEMPLATE_B, START_B)):
        my, mx = start
        for (dy, dx) in tmpl:
            y, x = my + dy, mx + dx
            if 0 <= y < H and 0 <= x < W:
                grid[y][x] = 5
    _diamond(grid, TARGET_A)
    _diamond(grid, TARGET_B)

    actions = [h["action"] for h in history[1:]] + [action]
    dx, dy = _offsets(actions)
    mark_a = (START_A[0], START_A[1] + dx)
    mark_b = (START_B[0] + dy, START_B[1])
    _draw(grid, TEMPLATE_A, mark_a)
    _draw(grid, TEMPLATE_B, mark_b)

    # bottom action bar filling with 4 from the right: round(64*n/50) cells after n clicks
    n = len(history)  # number of actions taken including this one
    filled = int(W * n / BAR_BUDGET + 0.5)
    filled = max(0, min(W, filled))
    for x in range(W):
        grid[H - 1][x] = 4 if x >= W - filled else 3

    state = "NOT_FINISHED"
    if mark_a == TARGET_A and mark_b == TARGET_B:
        levels += 1
        state = "NOT_FINISHED"

    return {
        "frame": base,
        "state": state,
        "levels_completed": levels,
        "available_actions": [6],
    }
