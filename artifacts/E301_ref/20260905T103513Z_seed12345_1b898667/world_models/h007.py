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


def _facing(g, top, left):
    def is_mark(y, x):
        return 0 <= y < BAR_ROW and 0 <= x < len(g[0]) and g[y][x] == MARK
    if any(is_mark(top, left + j) for j in range(4)):
        return 'u'
    if any(is_mark(top + 3, left + j) for j in range(4)):
        return 'd'
    if any(is_mark(top + i, left) for i in range(4)):
        return 'l'
    if any(is_mark(top + i, left + 3) for i in range(4)):
        return 'r'
    return 'd'  # mark hidden under the bar row


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

    # timer: after k actions, used cells = floor((8k + 12) / 25)
    k = len(history)
    used = (8 * k + 12) // 25
    for x in range(W):
        g[BAR_ROW][x] = BAR_BASE
    for i in range(min(used, W)):
        g[BAR_ROW][W - 1 - i] = BAR_USED
    if used >= W and result["state"] == "NOT_FINISHED":
        result["state"] = "GAME_OVER"

    result["frame"] = [g]
    return result
