H = W = 64
TR0, TC0, TN = 34, 27, 10          # target block (rows 34-43, cols 27-36)
MAX_DEPTH = 7
PAINT = 15

# Container tilted to the upper-left of the target (opening faces down-right), record 7.
TL_RUNS = {
    21: "5*24 2*1",
    22: "5*23 2*3",
    23: "5*22 2*2 15*1 2*2",
    24: "5*21 2*2 15*3 2*2",
    25: "5*20 2*2 15*5 2*2",
    26: "5*19 2*2 15*7 2*2",
    27: "5*18 2*2 15*9 2*2",
    28: "5*17 2*2 15*10",
    29: "5*16 2*2 15*10",
    30: "5*15 2*2 15*10",
    31: "5*14 2*2 15*10",
    32: "5*15 2*2 15*8",
    33: "5*16 2*2 15*6",
    34: "5*17 2*2 15*4",
    35: "5*18 2*2 15*2",
    36: "5*19 2*2",
    37: "5*20 2*1",
}


def _expand(runs):
    out = []
    for tok in runs.split():
        v, n = tok.split("*")
        out.extend([int(v)] * int(n))
    return out


def _cells_from_runs(runs_by_row):
    cells = []
    for r, runs in runs_by_row.items():
        row = _expand(runs)
        for c, v in enumerate(row):
            if v != 5:
                cells.append((r, c, v))
    return cells


def _upright():
    cells = []
    for c in range(25, 39):
        cells.append((24, c, 2))
    for r in range(25, 32):
        cells.append((r, 25, 2))
        cells.append((r, 38, 2))
        for c in range(26, 38):
            cells.append((r, c, 15))
    cells.append((32, 25, 2))
    cells.append((32, 38, 2))
    return cells


def _rot(cells):
    # 90 degrees clockwise about the target centre
    return [(c + 7, 70 - r, v) for (r, c, v) in cells]


def _rot_pos(p):
    px, py = p
    return (-py, px)


SPRITES = {}
_u = _upright()
_tl = _cells_from_runs(TL_RUNS)
_pu = (0, -1)
_ptl = (-1, -1)
for _k in range(4):
    SPRITES[_pu] = _u
    SPRITES[_ptl] = _tl
    _u = _rot(_u)
    _tl = _rot(_tl)
    _pu = _rot_pos(_pu)
    _ptl = _rot_pos(_ptl)


def _move(pos, a):
    px, py = pos
    if a == 1:
        py -= 1
    elif a == 2:
        py += 1
    elif a == 3:
        px -= 1
    elif a == 4:
        px += 1
    else:
        return pos
    px = max(-1, min(1, px))
    py = max(-1, min(1, py))
    if (px, py) == (0, 0):
        return pos
    return (px, py)


def _counter_cells(n):
    return max(0, min(W, (n * 64 + 50) // 100))


def _detect(last):
    for pos, cells in SPRITES.items():
        ok = True
        for (r, c, v) in cells:
            if last[r][c] != v:
                ok = False
                break
        if ok:
            return pos
    return None


def _replay(history):
    pos = (0, -1)
    for rec in history[1:]:
        act = rec.get("action") or {}
        pos = _move(pos, act.get("action"))
    return pos


def _base_frame(last, target, counter):
    g = [row[:] for row in last[:18]]
    for _ in range(18, 63):
        g.append([5] * W)
    g.append([4] * (W - counter) + [5] * counter)
    for dy in range(TN):
        for dx in range(TN):
            g[TR0 + dy][TC0 + dx] = target[dy][dx]
    return g


def _draw(g, cells, sy=0, sx=0):
    for (r, c, v) in cells:
        rr, cc = r + sy, c + sx
        if 0 <= rr < H and 0 <= cc < W:
            g[rr][cc] = v


def predict(history, action):
    prev = history[-1]
    last = prev["frame"][-1]
    a = action.get("action")

    target = [[last[TR0 + dy][TC0 + dx] for dx in range(TN)] for dy in range(TN)]
    pos = _detect(last)
    if pos is None:
        pos = _replay(history)
    counter = _counter_cells(len(history))

    frames = []
    if a in (1, 2, 3, 4):
        pos = _move(pos, a)
        g = _base_frame(last, target, counter)
        _draw(g, SPRITES[pos])
        frames = [g]
    elif a == 5:
        cells = SPRITES[pos]
        dy_, dx_ = -pos[1], -pos[0]
        painted = [row[:] for row in target]
        for (r, c, v) in cells:
            rr, cc = r + MAX_DEPTH * dy_, c + MAX_DEPTH * dx_
            if TR0 <= rr < TR0 + TN and TC0 <= cc < TC0 + TN:
                painted[rr - TR0][cc - TC0] = PAINT
        depths = list(range(0, MAX_DEPTH + 1)) + list(range(MAX_DEPTH - 1, -1, -1))
        for i, d in enumerate(depths):
            t = painted if i >= MAX_DEPTH else target
            g = _base_frame(last, t, counter)
            _draw(g, cells, d * dy_, d * dx_)
            frames.append(g)
    else:
        g = _base_frame(last, target, counter)
        _draw(g, SPRITES[pos])
        frames = [g]

    return {
        "frame": frames,
        "state": "NOT_FINISHED",
        "levels_completed": prev.get("levels_completed", 0),
        "available_actions": [1, 2, 3, 4, 5, 6],
    }
