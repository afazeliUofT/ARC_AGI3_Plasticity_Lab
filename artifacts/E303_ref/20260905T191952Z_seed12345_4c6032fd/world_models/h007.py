# GOAL: the player uses action 5 (interact) while facing a crate to push that 4x4 crate (border 4, centre 9) one step (4 cells) in the facing direction; the level is completed when all three crates lie fully inside the 12x4 bar (9 border, 2 interior) at rows 28-31, cols 28-39, i.e. every crate top-left has row 28 and col in {28,32,36}.
DIRS = {1: (-4, 0), 2: (4, 0), 3: (0, -4), 4: (0, 4)}


def _overlap(r1, c1, r2, c2):
    return r1 < r2 + 4 and r2 < r1 + 4 and c1 < c2 + 4 and c2 < c1 + 4


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
            if (g[y][x] in (3, 4) and g[y][x + 1] in (3, 4)
                    and g[y + 1][x] in (3, 4) and g[y + 1][x + 1] == 9):
                crates.append((y, x))
    return {"H": H, "W": W, "pr": pr, "pc": pc, "facing": facing,
            "br": br, "bc": bc, "crates": crates}


def _in_bounds(s, r, c):
    return 0 <= r and r + 4 <= s["H"] - 1 and 0 <= c and c + 4 <= s["W"]


def _crate_at(s, r, c, exclude=None):
    for i, (cr, cc) in enumerate(s["crates"]):
        if i != exclude and _overlap(r, c, cr, cc):
            return i
    return None


def _step(s, a):
    if a in DIRS:
        dr, dc = DIRS[a]
        s["facing"] = a
        nr, nc = s["pr"] + dr, s["pc"] + dc
        if not _in_bounds(s, nr, nc):
            return
        if _crate_at(s, nr, nc) is not None:
            return  # crates are solid; player just turns to face it
        s["pr"], s["pc"] = nr, nc
    elif a == 5:
        dr, dc = DIRS[s["facing"]]
        fr, fc = s["pr"] + dr, s["pc"] + dc
        i = _crate_at(s, fr, fc)
        if i is None:
            return
        cr, cc = s["crates"][i]
        tr, tc = cr + dr, cc + dc
        if not _in_bounds(s, tr, tc):
            return
        if _crate_at(s, tr, tc, exclude=i) is not None:
            return
        s["crates"][i] = (tr, tc)


def _won(s):
    br, bc = s["br"], s["bc"]
    if not s["crates"]:
        return False
    for (cr, cc) in s["crates"]:
        if not (cr == br and bc <= cc and cc + 4 <= bc + 12 and (cc - bc) % 4 == 0):
            return False
    return True


def _render(s, meter):
    H, W = s["H"], s["W"]
    g = [[1] * W for _ in range(H)]
    g[H - 1] = [7] * W
    for k in range(min(meter, W)):
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
    pr, pc, f = s["pr"], s["pc"], s["facing"]
    fdr, fdc = DIRS[f]
    faced = (pr + fdr, pc + fdc)
    for (cr, cc) in s["crates"]:
        border = 3 if (cr, cc) == faced else 4
        for y in range(cr, cr + 4):
            for x in range(cc, cc + 4):
                g[y][x] = border
        for y in range(cr + 1, cr + 3):
            for x in range(cc + 1, cc + 3):
                g[y][x] = 9
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
    _step(s, action["action"])
    # meter: 64-cell progress bar over a 200-action budget, rounded to nearest cell
    n_actions = len(history)
    meter = (64 * n_actions + 100) // 200
    win = _won(s)
    last = history[-1]
    lc = last["levels_completed"] + (1 if win else 0)
    return {"frame": _render(s, meter),
            "state": "NOT_FINISHED",
            "levels_completed": lc,
            "available_actions": last["available_actions"]}
