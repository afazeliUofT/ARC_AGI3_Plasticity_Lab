import copy

BG = 1
BODY = 14
MARK = 0
BAR_ROW = 63
BAR_COLOR = 7
BAR_USED = 4

DIRS = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}  # up, down, left, right


def _find_player(g):
    """Return (top, left, facing) of the 4x4 player block, facing in {'u','d','l','r'}."""
    cells = [(y, x) for y in range(len(g)) for x in range(len(g[0]))
             if g[y][x] == BODY or (g[y][x] == MARK and y < BAR_ROW)]
    ys = [c[0] for c in cells]
    xs = [c[1] for c in cells]
    top, left = min(ys), min(xs)
    # determine facing from position of MARK cells
    marks = [(y, x) for (y, x) in cells if g[y][x] == MARK]
    facing = 'u'
    if marks:
        my = {m[0] for m in marks}
        mx = {m[1] for m in marks}
        if len(my) == 1 and next(iter(my)) == top:
            facing = 'u'
        elif len(my) == 1 and next(iter(my)) == top + 3:
            facing = 'd'
        elif len(mx) == 1 and next(iter(mx)) == left:
            facing = 'l'
        elif len(mx) == 1 and next(iter(mx)) == left + 3:
            facing = 'r'
    return top, left, facing


def _draw_player(g, top, left, facing):
    for dy in range(4):
        for dx in range(4):
            g[top + dy][left + dx] = BODY
    if facing == 'u':
        for dx in range(4):
            g[top][left + dx] = MARK
    elif facing == 'd':
        for dx in range(4):
            g[top + 3][left + dx] = MARK
    elif facing == 'l':
        for dy in range(4):
            g[top + dy][left] = MARK
    elif facing == 'r':
        for dy in range(4):
            g[top + dy][left + 3] = MARK


def predict(history, action):
    last = history[-1]
    g = copy.deepcopy(last["frame"][0])
    H, W = len(g), len(g[0])
    a = action.get("action")

    result = {
        "state": last["state"],
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }

    if a in DIRS:
        top, left, facing = _find_player(g)
        dy, dx = DIRS[a]
        new_facing = {1: 'u', 2: 'd', 3: 'l', 4: 'r'}[a]
        nt, nl = top + 4 * dy, left + 4 * dx
        old_cells = {(top + i, left + j) for i in range(4) for j in range(4)}
        ok = 0 <= nt and nt + 3 < BAR_ROW and 0 <= nl and nl + 3 < W
        if ok:
            for i in range(4):
                for j in range(4):
                    y, x = nt + i, nl + j
                    if (y, x) in old_cells:
                        continue
                    if g[y][x] != BG:
                        ok = False
        # erase old player
        for (y, x) in old_cells:
            g[y][x] = BG
        if ok:
            top, left = nt, nl
        _draw_player(g, top, left, new_facing)

        # energy bar: count move actions so far (including this one)
        moves = sum(1 for r in history[1:] if r["action"] and r["action"]["action"] in DIRS) + 1
        used = 1 + (moves - 1) // 4
        for k in range(min(used, W)):
            g[BAR_ROW][W - 1 - k] = BAR_USED

    result["frame"] = [g]
    return result
