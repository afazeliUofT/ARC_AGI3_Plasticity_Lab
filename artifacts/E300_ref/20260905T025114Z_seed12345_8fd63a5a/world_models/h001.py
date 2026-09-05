import copy

H = W = 64
TR0, TC0, TN = 34, 27, 10          # target block (rows 34-43, cols 27-36)
CR0, CC0, CW, CH = 24, 25, 14, 9   # upright container (rows 24-32, cols 25-38)
MAX_DEPTH = 7

# Tilted container as drawn in the recording (only 2 / 15 cells are overlaid).
TILTED_RUNS = {
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


def _base_frame(last, target, counter):
    """Header rows copied, playfield cleared to 5 except target block, counter row."""
    g = [row[:] for row in last]
    for y in range(18, 63):
        g[y] = [5] * W
    for dy in range(TN):
        for dx in range(TN):
            g[TR0 + dy][TC0 + dx] = target[dy][dx]
    g[63] = [4] * (W - counter) + [5] * counter
    return g


def _draw_upright(g, d):
    y = CR0 + d
    for x in range(CC0, CC0 + CW):
        g[y][x] = 2
    for yy in range(y + 1, y + CH - 1):
        g[yy][CC0] = 2
        g[yy][CC0 + CW - 1] = 2
        for x in range(CC0 + 1, CC0 + CW - 1):
            g[yy][x] = 15
    yb = y + CH - 1
    g[yb][CC0] = 2
    g[yb][CC0 + CW - 1] = 2


def _draw_tilted(g):
    for y, runs in TILTED_RUNS.items():
        row = _expand(runs)
        for x, v in enumerate(row):
            if v in (2, 15):
                g[y][x] = v


def predict(history, action):
    prev = history[-1]
    last = prev["frame"][-1]
    a = action.get("action")

    target = [[last[TR0 + dy][TC0 + dx] for dx in range(TN)] for dy in range(TN)]
    counter = sum(1 for v in last[63] if v == 5)
    tilted = last[21][39] == 2

    frames = []

    if a == 4:
        counter = min(counter + 1, W)
        g = _base_frame(last, target, counter)
        _draw_tilted(g)
        frames = [g]
    elif a == 3:
        g = _base_frame(last, target, counter)
        _draw_upright(g, 0)
        frames = [g]
    elif a == 5:
        counter = min(counter + 1, W)
        if tilted:
            g = _base_frame(last, target, counter)
            _draw_tilted(g)
            frames = [g]
        else:
            offsets = list(range(0, MAX_DEPTH + 1)) + list(range(MAX_DEPTH - 1, -1, -1))
            reached = False
            for d in offsets:
                if d == MAX_DEPTH:
                    reached = True
                    # liquid rows at max depth stamp the target
                    lo = CR0 + 1 + MAX_DEPTH
                    hi = CR0 + CH - 2 + MAX_DEPTH
                    for y in range(max(lo, TR0), min(hi, TR0 + TN - 1) + 1):
                        for dx in range(TN):
                            target[y - TR0][dx] = 15
                g = _base_frame(last, target, counter)
                _draw_upright(g, d)
                frames.append(g)
    elif a == 6:
        counter = min(counter + 1, W)
        g = _base_frame(last, target, counter)
        if tilted:
            _draw_tilted(g)
        else:
            _draw_upright(g, 0)
        frames = [g]
    else:
        g = _base_frame(last, target, counter)
        if tilted:
            _draw_tilted(g)
        else:
            _draw_upright(g, 0)
        frames = [g]

    return {
        "frame": frames,
        "state": "NOT_FINISHED",
        "levels_completed": prev.get("levels_completed", 0),
        "available_actions": [1, 2, 3, 4, 5, 6],
    }
