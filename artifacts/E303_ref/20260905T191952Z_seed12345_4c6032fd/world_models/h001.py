# GOAL: the 4x4 player block (values 14 with a 0 facing edge) moves fully inside the 12x4 rectangle of 9/2 cells at rows 28-31, cols 24-35, which completes the level.
import copy

GOAL_R0, GOAL_R1, GOAL_C0, GOAL_C1 = 28, 31, 24, 35
DIRS = {1: (-4, 0), 2: (4, 0), 3: (0, -4), 4: (0, 4)}


def _find_player(g):
    rows = [y for y in range(len(g)) for x in range(len(g[0])) if g[y][x] in (0, 14)]
    cols = [x for y in range(len(g)) for x in range(len(g[0])) if g[y][x] in (0, 14)]
    return min(rows), min(cols)


def predict(history, action):
    last = history[-1]
    frame = copy.deepcopy(last["frame"])
    g = frame[0]
    lc = last["levels_completed"]
    a = action["action"]
    out = {"frame": frame, "state": last["state"], "levels_completed": lc,
           "available_actions": last["available_actions"]}
    if a not in DIRS:
        return out

    H, W = len(g), len(g[0])
    r0, c0 = _find_player(g)
    dr, dc = DIRS[a]
    nr, nc = r0 + dr, c0 + dc

    # move counter -> bottom bar cell turns 4 every 3rd move starting with the first
    m = 1 + sum(1 for h in history[1:] if h["action"] and h["action"]["action"] in DIRS)
    if (m - 1) % 3 == 0:
        col = 63 - (m - 1) // 3
        if 0 <= col < W:
            g[H - 1][col] = 4

    ok = 0 <= nr and nr + 3 <= H - 2 and 0 <= nc and nc + 3 < W
    if ok:
        for y in range(nr, nr + 4):
            for x in range(nc, nc + 4):
                if g[y][x] not in (1, 9, 2, 0, 14):
                    ok = False
    if ok:
        for y in range(r0, r0 + 4):
            for x in range(c0, c0 + 4):
                g[y][x] = 1
        for y in range(nr, nr + 4):
            for x in range(nc, nc + 4):
                g[y][x] = 14
        if a == 1:
            for x in range(nc, nc + 4):
                g[nr][x] = 0
        elif a == 2:
            for x in range(nc, nc + 4):
                g[nr + 3][x] = 0
        elif a == 3:
            for y in range(nr, nr + 4):
                g[y][nc] = 0
        else:
            for y in range(nr, nr + 4):
                g[y][nc + 3] = 0
        if GOAL_R0 <= nr and nr + 3 <= GOAL_R1 and GOAL_C0 <= nc and nc + 3 <= GOAL_C1:
            out["levels_completed"] = lc + 1
            out["state"] = "NOT_FINISHED"
    return out
