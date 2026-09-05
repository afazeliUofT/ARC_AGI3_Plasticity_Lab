import copy

BG = 1
BODY = 14
MARK = 0
BAR_ROW = 63
BAR_BASE = 7
BAR_USED = 4
NOOP = 5

# timer model: bar cell = 12 units; initial 6 units; a direction action
# (moved or blocked) costs 4 units, a no-op costs 3 units.
UNIT_CELL = 12
T0 = 6
COST_DIR = 4
COST_NOOP = 3

DIRS = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}  # up, down, left, right
FACE = {1: 'u', 2: 'd', 3: 'l', 4: 'r'}


def _find_player(g):
    cells = [(y, x) for y in range(BAR_ROW) for x in range(len(g[0]))
             if g[y][x] == BODY or g[y][x] == MARK]
    if not cells:
        return None
    ys = [c[0] for c in cells]
    xs = [c[1] for c in cells]
    return min(ys), min(xs)


def _draw_player(g, top, left, facing):
    H = len(g)
    for dy in range(4):
        for dx in range(4):
            if top + dy < BAR_ROW:
                g[top + dy][left + dx] = BODY
    if facing == 'u':
        for dx in range(4):
            if top < BAR_ROW:
                g[top][left + dx] = MARK
    elif facing == 'd':
        for dx in range(4):
            if top + 3 < BAR_ROW:
                g[top + 3][left + dx] = MARK
    elif facing == 'l':
        for dy in range(4):
            if top + dy < BAR_ROW:
                g[top + dy][left] = MARK
    elif facing == 'r':
        for dy in range(4):
            if top + dy < BAR_ROW:
                g[top + dy][left + 3] = MARK


def _timer_units(history, action):
    acts = [h["action"]["action"] for h in history[1:] if h.get("action")]
    acts.append(action.get("action"))
    t = T0
    for a in acts:
        if a == NOOP:
            t += COST_NOOP
        elif a in DIRS:
            t += COST_DIR
        else:
            t += COST_DIR
    return t


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
        pos = _find_player(g)
        if pos is not None:
            top, left = pos
            dy, dx = DIRS[a]
            new_facing = FACE[a]
            nt, nl = top + 4 * dy, left + 4 * dx
            old_cells = {(top + i, left + j) for i in range(4) for j in range(4)}
            ok = 0 <= nt and nt + 3 < H and 0 <= nl and nl + 3 < W
            if ok:
                for i in range(4):
                    for j in range(4):
                        y, x = nt + i, nl + j
                        if (y, x) in old_cells or y >= BAR_ROW:
                            continue
                        if g[y][x] != BG:
                            ok = False
            for (y, x) in old_cells:
                if y < BAR_ROW:
                    g[y][x] = BG
            if ok:
                top, left = nt, nl
            _draw_player(g, top, left, new_facing)

    t = _timer_units(history, action)
    used = t // UNIT_CELL
    for x in range(W):
        g[BAR_ROW][x] = BAR_BASE
    for k in range(min(used, W)):
        g[BAR_ROW][W - 1 - k] = BAR_USED
    if used >= W and result["state"] == "NOT_FINISHED":
        result["state"] = "GAME_OVER"

    result["frame"] = [g]
    return result
