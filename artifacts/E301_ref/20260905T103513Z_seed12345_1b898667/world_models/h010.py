import copy

BG = 1
BODY = 14
MARK = 0
BAR_ROW = 63
BAR_BASE = 7
BAR_USED = 4

DIRS = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}  # up, down, left, right
FACE = {1: 'u', 2: 'd', 3: 'l', 4: 'r'}


def _find_player(g):
    cells = [(y, x) for y in range(BAR_ROW) for x in range(len(g[0]))
             if g[y][x] == BODY or g[y][x] == MARK]
    if not cells:
        return None
    top = min(c[0] for c in cells)
    left = min(c[1] for c in cells)
    return top, left


def _draw_player(g, top, left, facing):
    W = len(g[0])
    for dy in range(4):
        for dx in range(4):
            y, x = top + dy, left + dx
            if 0 <= y < BAR_ROW and 0 <= x < W:
                g[y][x] = BODY
    if facing == 'u':
        marks = [(top, left + j) for j in range(4)]
    elif facing == 'd':
        marks = [(top + 3, left + j) for j in range(4)]
    elif facing == 'l':
        marks = [(top + i, left) for i in range(4)]
    else:
        marks = [(top + i, left + 3) for i in range(4)]
    for y, x in marks:
        if 0 <= y < BAR_ROW and 0 <= x < W:
            g[y][x] = MARK


def _last_reset_index(history):
    for i in range(len(history) - 1, -1, -1):
        a = history[i].get("action")
        if a is None or a.get("action") == 0:
            return i
    return 0


def predict(history, action):
    last = history[-1]
    a = action.get("action")

    # Reset: restore the initial observation of the level.
    if a == 0:
        first = history[0]
        return {
            "frame": copy.deepcopy(first["frame"]),
            "state": "NOT_FINISHED",
            "levels_completed": first["levels_completed"],
            "available_actions": list(first["available_actions"]),
        }

    g = copy.deepcopy(last["frame"][0])
    H, W = len(g), len(g[0])

    result = {
        "state": last["state"],
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }

    # Game over: once the timer bar is completely used up (or state already over),
    # nothing changes and the state becomes GAME_OVER.
    bar_full = all(g[BAR_ROW][x] == BAR_USED for x in range(W))
    if last["state"] == "GAME_OVER" or bar_full:
        result["state"] = "GAME_OVER"
        result["frame"] = [g]
        return result

    if a in DIRS:
        pos = _find_player(g)
        if pos is not None:
            top, left = pos
            dy, dx = DIRS[a]
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
                if 0 <= y < BAR_ROW and 0 <= x < W:
                    g[y][x] = BG
            if ok:
                top, left = nt, nl
            _draw_player(g, top, left, FACE[a])

    # timer: after k actions since the last reset, used cells = floor((8k + 12) / 25)
    r = _last_reset_index(history)
    k = len(history) - r
    used = min((8 * k + 12) // 25, W)
    for x in range(W):
        g[BAR_ROW][x] = BAR_BASE
    for i in range(used):
        g[BAR_ROW][W - 1 - i] = BAR_USED

    result["frame"] = [g]
    return result
