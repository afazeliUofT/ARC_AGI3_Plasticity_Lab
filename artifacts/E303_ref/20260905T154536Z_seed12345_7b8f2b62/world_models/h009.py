# GOAL: the level is completed when the 13-coloured head cell at the tip of the four-segment arm (segments coloured 12 right, 10 up, 11 right, 14 down, each grown/shrunk by 3 cells via the right/left half of the button box of its colour, a click being ignored if the arm would then overlap a 15-coloured wall or leave the grid) lands on the hollow diamond centre at row 31, column 52.
import copy

STEP = 3
MIN_LEN = 2
BUDGET_L1 = 50
BUDGET_L2 = 200
H = 64
W = 64


def _click(act):
    if act is None or act.get("action") != 6:
        return None
    d = act.get("data") or {}
    if "x" not in d or "y" not in d:
        return None
    return d["x"], d["y"]


def _counter(grid, n, budget):
    filled = int(W * n / budget + 0.5)
    filled = max(0, min(W, filled))
    for x in range(W):
        grid[H - 1][x] = 4 if x >= W - filled else 3


# ---------------------------------------------------------------- level 1
L1_HBOX = (18, 24, 36, 48, 42)   # y0, y1, x0, x1, split column
L1_VBOX = (35, 47, 21, 27, 41)   # y0, y1, x0, x1, split row
L1_HDIAMOND = ((9, 52), (11, 52), (10, 51), (10, 53))
L1_VDIAMOND = ((51, 10), (53, 10), (52, 9), (52, 11))


def _l1_button(act):
    c = _click(act)
    if c is None:
        return None
    x, y = c
    y0, y1, x0, x1, split = L1_HBOX
    if y0 <= y <= y1 and x0 <= x <= x1:
        if x < split:
            return "left"
        if x > split:
            return "right"
        return None
    y0, y1, x0, x1, split = L1_VBOX
    if y0 <= y <= y1 and x0 <= x <= x1:
        if y < split:
            return "up"
        if y > split:
            return "down"
        return None
    return None


def _l1_lengths(actions):
    la, lb = 5, 8
    for act in actions:
        b = _l1_button(act)
        if b == "left":
            la = max(MIN_LEN, la - STEP)
        elif b == "right":
            la = min(36, la + STEP)
        elif b == "up":
            lb = max(MIN_LEN, lb - STEP)
        elif b == "down":
            lb = min(35, lb + STEP)
    return la, lb


def _l1_render(base, la, lb, n):
    grid = copy.deepcopy(base)
    for y in (9, 10, 11):
        for x in range(28, W):
            grid[y][x] = 5
        for x in range(28, 28 + la):
            grid[y][x] = 14
    grid[10][28 + la - 2] = 13
    for (y, x) in L1_HDIAMOND:
        grid[y][x] = 13
    for x in (9, 10, 11):
        for y in range(28, H - 1):
            grid[y][x] = 5
        for y in range(28, 28 + lb):
            grid[y][x] = 11
    grid[28 + lb - 2][10] = 13
    for (y, x) in L1_VDIAMOND:
        grid[y][x] = 13
    _counter(grid, n, BUDGET_L1)
    return grid


# ---------------------------------------------------------------- level 2
L2_BOXES = [(3, 12), (18, 10), (33, 11), (48, 14)]   # x0, colour; rows 54..60, width 13
L2_BOX_Y0, L2_BOX_Y1 = 54, 60
L2_DIAMOND = ((30, 52), (32, 52), (31, 51), (31, 53))
L2_TARGET = (31, 52)


def _l2_walls():
    walls = set()
    for y in (9, 10, 11):
        for x in range(33, 57):
            walls.add((y, x))
    for y in range(12, 27):
        for x in (33, 34, 35):
            walls.add((y, x))
    for y in range(15, 45):
        for x in (42, 43, 44):
            walls.add((y, x))
    return walls


L2_WALLS = _l2_walls()


def _l2_button(act):
    c = _click(act)
    if c is None:
        return None
    x, y = c
    if not (L2_BOX_Y0 <= y <= L2_BOX_Y1):
        return None
    for i, (x0, _col) in enumerate(L2_BOXES):
        if x0 <= x <= x0 + 12:
            split = x0 + 6
            if x < split:
                return (i, -1)
            if x > split:
                return (i, +1)
            return None
    return None


def _arm(L):
    r0, c0 = 40, 10
    e0 = c0 + L[0] - 1
    seg0 = {(y, x) for y in (r0 - 1, r0, r0 + 1) for x in range(c0, e0 + 1)}
    base0 = {(y, c0 - 1) for y in (r0 - 1, r0, r0 + 1)}
    c1 = e0 + 2
    e1 = r0 - L[1] + 1
    seg1 = {(y, x) for x in (c1 - 1, c1, c1 + 1) for y in range(e1, r0 + 1)}
    base1 = {(r0 + 1, x) for x in (c1 - 1, c1, c1 + 1)}
    r2 = e1 - 2
    e2 = c1 + L[2] - 1
    seg2 = {(y, x) for y in (r2 - 1, r2, r2 + 1) for x in range(c1, e2 + 1)}
    base2 = {(y, c1 - 1) for y in (r2 - 1, r2, r2 + 1)}
    c3 = e2 + 2
    e3 = r2 + L[3] - 1
    seg3 = {(y, x) for x in (c3 - 1, c3, c3 + 1) for y in range(r2, e3 + 1)}
    base3 = {(r2 - 1, x) for x in (c3 - 1, c3, c3 + 1)}
    head = (e3 - 1, c3)
    return {
        "segs": [(12, seg0), (10, seg1), (11, seg2), (14, seg3)],
        "bases": [base0, base1, base2, base3],
        "head": head,
    }


def _l2_valid(L):
    if any(l < MIN_LEN for l in L):
        return False
    arm = _arm(L)
    cells = set()
    for _col, s in arm["segs"]:
        cells |= s
    for b in arm["bases"]:
        cells |= b
    for (y, x) in cells:
        if y < 0 or y > H - 2 or x < 0 or x > W - 1:
            return False
        if (y, x) in L2_WALLS:
            return False
    return True


def _l2_lengths(actions):
    L = [2, 2, 2, 2]
    for act in actions:
        b = _l2_button(act)
        if b is None:
            continue
        i, s = b
        nl = list(L)
        nl[i] = nl[i] + s * STEP
        if _l2_valid(nl):
            L = nl
    return L


def _l2_render(L, n):
    grid = [[5] * W for _ in range(H)]
    for (y, x) in L2_WALLS:
        grid[y][x] = 15
    arm = _arm(L)
    for base in arm["bases"]:
        for (y, x) in base:
            grid[y][x] = 3
    for col, cells in arm["segs"]:
        for (y, x) in cells:
            grid[y][x] = col
    hy, hx = arm["head"]
    grid[hy][hx] = 13
    for (y, x) in L2_DIAMOND:
        grid[y][x] = 13
    for (x0, c) in L2_BOXES:
        rows = [
            [2] * 13,
            [2] + [4] * 5 + [3] + [4] * 5 + [2],
            [2, 4, c, c, c, 4, 3, 4, c, c, c, 4, 2],
            [2, 4, c, 4, 4, 4, 3, 4, 4, 4, c, 4, 2],
            [2, 4, c, c, c, 4, 3, 4, c, c, c, 4, 2],
            [2] + [4] * 5 + [3] + [4] * 5 + [2],
            [2] * 13,
        ]
        for dy, row in enumerate(rows):
            for dx, v in enumerate(row):
                grid[L2_BOX_Y0 + dy][x0 + dx] = v
    _counter(grid, n, BUDGET_L2)
    return grid


# ---------------------------------------------------------------- predict
def predict(history, action):
    last = history[-1]
    lc = last["levels_completed"]

    if lc == 0:
        actions = [h["action"] for h in history[1:]] + [action]
        la, lb = _l1_lengths(actions)
        grid = _l1_render(history[0]["frame"][0], la, lb, len(actions))
        if 28 + la - 2 == 52 and 28 + lb - 2 == 52:
            return {
                "frame": [grid, _l2_render([2, 2, 2, 2], 0)],
                "state": "NOT_FINISHED",
                "levels_completed": 1,
                "available_actions": [6],
            }
        return {
            "frame": [grid],
            "state": "NOT_FINISHED",
            "levels_completed": 0,
            "available_actions": [6],
        }

    if lc == 1:
        k = 0
        for i, h in enumerate(history):
            if h["levels_completed"] >= 1:
                k = i
                break
        actions = [h["action"] for h in history[k + 1:]] + [action]
        L = _l2_lengths(actions)
        grid = _l2_render(L, len(actions))
        head = _arm(L)["head"]
        levels = 1
        state = "NOT_FINISHED"
        if head == L2_TARGET:
            levels = 2
            state = "NOT_FINISHED"
        return {
            "frame": [grid],
            "state": state,
            "levels_completed": levels,
            "available_actions": [6],
        }

    return {
        "frame": copy.deepcopy(last["frame"]),
        "state": last["state"],
        "levels_completed": lc,
        "available_actions": [6],
    }
