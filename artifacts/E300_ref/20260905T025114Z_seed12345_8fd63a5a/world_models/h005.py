H = W = 64
TR0, TC0, TN = 34, 27, 10          # target block (rows 34-43, cols 27-36)
MAX_DEPTH = 7

# Container tilted to the right (opening faces down-left), as drawn in record 1.
TILTED_RIGHT_RUNS = {
    21: "5*39 2*1 5*24",
    22: "5*38 2*3 5*23",
    23: "5*37 2*2 15*1 2*2 5*22",
    24: "5*36 2*2 15*3 2*2 5*21",
    25: "5*35 2*2 15*5 2*2 5*20",
    26: "5*34 2*2 15*7 2*2 5*19",
    27: "5*33 2*2 15*9 2*2 5*18",
    28: "5*35 15*10 2*2 5*17",
    29: "5*36 15*10 2*2 5*16",
    30: "5*37 15*10 2*2 5*15",
    31: "5*38 15*10 2*2 5*14",
    32: "5*39 15*8 2*2 5*15",
    33: "5*40 15*6 2*2 5*16",
    34: "5*27 0*10 5*4 15*4 2*2 5*17",
    35: "5*27 0*10 5*5 15*2 2*2 5*18",
    36: "5*27 0*10 5*6 2*2 5*19",
    37: "5*27 0*10 5*6 2*1 5*20",
}


def _expand(runs):
    out = []
    for tok in runs.split():
        v, n = tok.split("*")
        out.extend([int(v)] * int(n))
    return out


def _tr_cells():
    cells = []
    for y, runs in TILTED_RIGHT_RUNS.items():
        row = _expand(runs)
        for x, v in enumerate(row):
            if v in (2, 15):
                cells.append((y, x, v))
    return cells


def _upright_cells():
    y0, x0, w, h = 24, 25, 14, 9
    cells = []
    for x in range(x0, x0 + w):
        cells.append((y0, x, 2))
    for y in range(y0 + 1, y0 + h - 1):
        cells.append((y, x0, 2))
        cells.append((y, x0 + w - 1, 2))
        for x in range(x0 + 1, x0 + w - 1):
            cells.append((y, x, 15))
    cells.append((y0 + h - 1, x0, 2))
    cells.append((y0 + h - 1, x0 + w - 1, 2))
    return cells


def _left_cells():
    # lying on the left of the target, opening faces right (record 10)
    y0, x0, w, h = 32, 17, 9, 14
    cells = []
    for y in range(y0, y0 + h):
        cells.append((y, x0, 2))
    for x in range(x0 + 1, x0 + w):
        cells.append((y0, x, 2))
        cells.append((y0 + h - 1, x, 2))
    for y in range(y0 + 1, y0 + h - 1):
        for x in range(x0 + 1, x0 + w - 1):
            cells.append((y, x, 15))
    return cells


def _hflip(cells):
    return [(y, W - 1 - x, v) for (y, x, v) in cells]


def _vflip(cells):
    # flip about the target's vertical centre (rows 34-43 -> centre 38.5)
    return [(77 - y, x, v) for (y, x, v) in cells]


_U = _upright_cells()
_TR = _tr_cells()
_TL = _hflip(_TR)
_LL = _left_cells()
_LR = _hflip(_LL)

# angle -> (sprite cells, direction of the opening / press direction)
ORIENT = {
    0: (_U, (1, 0)),
    45: (_TR, (1, -1)),
    -45: (_TL, (1, 1)),
    -90: (_LL, (0, 1)),
    90: (_LR, (0, -1)),
    -180: (_vflip(_U), (-1, 0)),
    135: (_vflip(_TL), (-1, -1)),
    -135: (_vflip(_TR), (-1, 1)),
}

ANGLES = [-180, -135, -90, -45, 0, 45, 90, 135]
ACTION_TARGET = {1: 0, 2: -180, 3: -90, 4: 90}


def _counter_cells(n):
    return max(0, min(W, (n * 64 + 50) // 100))


def _detect(last):
    for ang in ANGLES:
        cells = ORIENT[ang][0]
        ok = True
        for (y, x, v) in cells:
            if last[y][x] != v:
                ok = False
                break
        if ok:
            return ang
    return 0


def _base_frame(last, target, counter):
    g = [row[:] for row in last[:18]]
    for _ in range(18, 63):
        g.append([5] * W)
    g.append([4] * (W - counter) + [5] * counter)
    for dy in range(TN):
        for dx in range(TN):
            g[TR0 + dy][TC0 + dx] = target[dy][dx]
    return g


def _draw(g, ang, shift=(0, 0)):
    cells = ORIENT[ang][0]
    sy, sx = shift
    for (y, x, v) in cells:
        yy, xx = y + sy, x + sx
        if 0 <= yy < H and 0 <= xx < W:
            g[yy][xx] = v


def predict(history, action):
    prev = history[-1]
    last = prev["frame"][-1]
    a = action.get("action")

    target = [[last[TR0 + dy][TC0 + dx] for dx in range(TN)] for dy in range(TN)]
    ang = _detect(last)
    n_actions = len(history)
    counter = _counter_cells(n_actions)

    frames = []

    if a in ACTION_TARGET:
        tgt = ACTION_TARGET[a]
        if tgt > ang:
            ang = min(ang + 45, 135)
        elif tgt < ang:
            ang = max(ang - 45, -180)
        g = _base_frame(last, target, counter)
        _draw(g, ang)
        frames = [g]
    elif a == 5:
        cells, (dy_, dx_) = ORIENT[ang]
        # paint: target cells covered by the container interior at full depth
        painted = [row[:] for row in target]
        for (y, x, v) in cells:
            if v == 15:
                yy, xx = y + MAX_DEPTH * dy_, x + MAX_DEPTH * dx_
                if TR0 <= yy < TR0 + TN and TC0 <= xx < TC0 + TN:
                    painted[yy - TR0][xx - TC0] = 15
        depths = list(range(0, MAX_DEPTH + 1)) + list(range(MAX_DEPTH - 1, -1, -1))
        for i, d in enumerate(depths):
            t = painted if i >= MAX_DEPTH else target
            g = _base_frame(last, t, counter)
            _draw(g, ang, (d * dy_, d * dx_))
            frames.append(g)
    else:
        g = _base_frame(last, target, counter)
        _draw(g, ang)
        frames = [g]

    return {
        "frame": frames,
        "state": "NOT_FINISHED",
        "levels_completed": prev.get("levels_completed", 0),
        "available_actions": [1, 2, 3, 4, 5, 6],
    }
