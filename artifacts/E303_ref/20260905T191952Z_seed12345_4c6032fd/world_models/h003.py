# GOAL: the player pushes all three 4x4 crates (4 border, 9 centre) into the 12x4 bar region (9 border, 2 interior) so every crate lies fully inside the bar, which completes the level.
DIRS = {1: (-4, 0), 2: (4, 0), 3: (0, -4), 4: (0, 4)}


def _overlap(r1, c1, h1, w1, r2, c2, h2, w2):
    return r1 < r2 + h2 and r2 < r1 + h1 and c1 < c2 + w2 and c2 < c1 + w1


def _parse(frame):
    g = frame[0]
    H, W = len(g), len(g[0])
    cells = [(y, x) for y in range(H - 1) for x in range(W) if g[y][x] in (0, 14)]
    pr = min(y for y, x in cells)
    pc = min(x for y, x in cells)
    if g[pr][pc] == 0 and g[pr][pc + 3] == 0:
        facing = 1
    elif g[pr + 3][pc] == 0 and g[pr + 3][pc + 3] == 0:
        facing = 2
    elif g[pr][pc] == 0:
        facing = 3
    else:
        facing = 4
    twos = [(y, x) for y in range(H - 1) for x in range(W) if g[y][x] == 2]
    br = min(y for y, x in twos) - 1
    bc = min(x for y, x in twos) - 1
    crates = []
    for y in range(H - 4):
        for x in range(W - 3):
            if g[y][x] == 4 and g[y][x + 1] == 4 and g[y + 1][x] == 4 and g[y + 1][x + 1] == 9:
                crates.append((y, x))
    return {"H": H, "W": W, "pr": pr, "pc": pc, "facing": facing,
            "br": br, "bc": bc, "crates": crates, "moves": 0}


def _in_bounds(s, r, c):
    return 0 <= r and r + 4 <= s["H"] - 1 and 0 <= c and c + 4 <= s["W"]


def _step(s, a):
    if a not in DIRS:
        return False
    s["moves"] += 1
    dr, dc = DIRS[a]
    s["facing"] = a
    nr, nc = s["pr"] + dr, s["pc"] + dc
    if not _in_bounds(s, nr, nc):
        return False
    # find crate the player would move into
    hit = None
    for i, (cr, cc) in enumerate(s["crates"]):
        if _overlap(nr, nc, 4, 4, cr, cc, 4, 4):
            hit = i
            break
    if hit is not None:
        cr, cc = s["crates"][hit]
        tr, tc = cr + dr, cc + dc
        if not _in_bounds(s, tr, tc):
            return False
        for j, (or_, oc) in enumerate(s["crates"]):
            if j != hit and _overlap(tr, tc, 4, 4, or_, oc, 4, 4):
                return False
        s["crates"][hit] = (tr, tc)
    s["pr"], s["pc"] = nr, nc
    br, bc = s["br"], s["bc"]
    for (cr, cc) in s["crates"]:
        if not (cr == br and bc <= cc and cc + 4 <= bc + 12):
            return False
    return True


def _render(s):
    H, W = s["H"], s["W"]
    g = [[1] * W for _ in range(H)]
    g[H - 1] = [7] * W
    ticks = (s["moves"] + 2) // 3
    for k in range(min(ticks, W)):
        g[H - 1][W - 1 - k] = 4
    br, bc = s["br"], s["bc"]
    for y in range(br, br + 4):
        for x in range(bc, bc + 12):
            if 0 <= x < W:
                g[y][x] = 9
    for y in range(br + 1, br + 3):
        for x in range(bc + 1, bc + 11):
            if 0 <= x < W:
                g[y][x] = 2
    for (cr, cc) in s["crates"]:
        for y in range(cr, cr + 4):
            for x in range(cc, cc + 4):
                g[y][x] = 4
        for y in range(cr + 1, cr + 3):
            for x in range(cc + 1, cc + 3):
                g[y][x] = 9
    pr, pc, f = s["pr"], s["pc"], s["facing"]
    for y in range(pr, pr + 4):
        for x in range(pc, pc + 4):
            g[y][x] = 14
    if f == 1:
        for x in range(pc, pc + 4):
            g[pr][x] = 0
    elif f == 2:
        for x in range(pc, pc + 4):
            g[pr + 3][x] = 0
    elif f == 3:
        for y in range(pr, pr + 4):
            g[y][pc] = 0
    else:
        for y in range(pr, pr + 4):
            g[y][pc + 3] = 0
    return [g]


def predict(history, action):
    s = _parse(history[0]["frame"])
    for h in history[1:]:
        if h.get("action"):
            _step(s, h["action"]["action"])
    win = _step(s, action["action"])
    last = history[-1]
    lc = last["levels_completed"] + (1 if win else 0)
    return {"frame": _render(s),
            "state": "NOT_FINISHED",
            "levels_completed": lc,
            "available_actions": last["available_actions"]}
