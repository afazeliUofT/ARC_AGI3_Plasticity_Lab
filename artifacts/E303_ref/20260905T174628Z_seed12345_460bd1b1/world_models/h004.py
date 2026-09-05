# GOAL: The level is completed when the 10x10 block (rows 34-43, cols 27-36) exactly matches the target picture in the top-left panel (rows 3-12, cols 3-12); an upright pour paints the topmost 5-row layer of the block whose colour differs from the cup's colour, so pouring white twice (filling both layers) and then black once (repainting the top layer) yields top five rows 0 / bottom five rows 15, which completes the level.

BLOCK_R0, BLOCK_C0 = 34, 27
TARGET_R0, TARGET_C0 = 3, 3
CUP_TOP = 24
AVAIL = [1, 2, 3, 4, 5, 6]

# right-tilted cup, absolute coordinates: (col_start, col_end, 'w'=wall/'l'=liquid)
DIAMOND = {
    21: [(39, 39, 'w')],
    22: [(38, 40, 'w')],
    23: [(37, 38, 'w'), (39, 39, 'l'), (40, 41, 'w')],
    24: [(36, 37, 'w'), (38, 40, 'l'), (41, 42, 'w')],
    25: [(35, 36, 'w'), (37, 41, 'l'), (42, 43, 'w')],
    26: [(34, 35, 'w'), (36, 42, 'l'), (43, 44, 'w')],
    27: [(33, 34, 'w'), (35, 43, 'l'), (44, 45, 'w')],
    28: [(35, 44, 'l'), (45, 46, 'w')],
    29: [(36, 45, 'l'), (46, 47, 'w')],
    30: [(37, 46, 'l'), (47, 48, 'w')],
    31: [(38, 47, 'l'), (48, 49, 'w')],
    32: [(39, 46, 'l'), (47, 48, 'w')],
    33: [(40, 45, 'l'), (46, 47, 'w')],
    34: [(41, 44, 'l'), (45, 46, 'w')],
    35: [(42, 43, 'l'), (44, 45, 'w')],
    36: [(43, 44, 'w')],
    37: [(43, 43, 'w')],
}


def _pour(block, color):
    nb = [row[:] for row in block]
    for layer in range(2):
        rows = range(layer * 5, layer * 5 + 5)
        if any(nb[r][c] != color for r in rows for c in range(10)):
            for r in rows:
                nb[r] = [color] * 10
            break
    return nb


def _upright_cells(color, y0):
    cells = []
    for x in range(25, 39):
        cells.append((y0, x, 2))
    for y in range(y0 + 1, y0 + 8):
        cells.append((y, 25, 2))
        cells.append((y, 38, 2))
        for x in range(26, 38):
            cells.append((y, x, color))
    cells.append((y0 + 8, 25, 2))
    cells.append((y0 + 8, 38, 2))
    return cells


def _tilted_cells(color, orient):
    cells = []
    for row, runs in DIAMOND.items():
        for c0, c1, kind in runs:
            v = 2 if kind == 'w' else color
            for x in range(c0, c1 + 1):
                xx = x if orient > 0 else 63 - x
                cells.append((row, xx, v))
    return cells


def _counter(n):
    return (128 * n + 100) // 200


def _render(template, orient, color, block, n, cup_top=CUP_TOP):
    g = [row[:] for row in template[:18]] + [[5] * 64 for _ in range(46)]
    for x in range(35, 46):
        g[7][x] = 3
    xs = range(35, 40) if color == 0 else range(41, 46)
    for x in xs:
        g[7][x] = 0
    for i in range(10):
        for j in range(10):
            g[BLOCK_R0 + i][BLOCK_C0 + j] = block[i][j]
    cells = _upright_cells(color, cup_top) if orient == 0 else _tilted_cells(color, orient)
    for (y, x, v) in cells:
        if 18 <= y < 63 and 0 <= x < 64:
            g[y][x] = v
    c = max(0, min(64, _counter(n)))
    g[63] = [4] * (64 - c) + [5] * c
    return g


def _step(template, orient, color, block, n, action):
    a = action.get("action")
    data = action.get("data") or {}
    n += 1
    frames = None
    if a == 4:
        orient = min(1, orient + 1)
    elif a == 3:
        orient = max(-1, orient - 1)
    elif a == 5:
        if orient == 0:
            new_block = _pour(block, color)
            frames = []
            for k in range(15):
                cup_row = CUP_TOP + k if k <= 7 else CUP_TOP + (14 - k)
                blk = block if k <= 7 else new_block
                frames.append(_render(template, orient, color, blk, n, cup_row))
            block = new_block
    elif a == 6:
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            if 3 <= y <= 5 and 35 <= x <= 39:
                color = 0
            elif 3 <= y <= 5 and 41 <= x <= 45:
                color = 15
    if frames is None:
        frames = [_render(template, orient, color, block, n)]
    return orient, color, block, n, frames


def _target(template):
    return [[template[TARGET_R0 + i][TARGET_C0 + j] for j in range(10)] for i in range(10)]


def predict(history, action):
    template = history[0]["frame"][0]
    orient, color, n = 0, 15, 0
    block = [[template[BLOCK_R0 + i][BLOCK_C0 + j] for j in range(10)] for i in range(10)]
    for rec in history[1:]:
        a = rec.get("action")
        if a is None:
            continue
        orient, color, block, n, _ = _step(template, orient, color, block, n, a)
    orient, color, block, n, frames = _step(template, orient, color, block, n, action)
    target = _target(template)
    levels = history[-1]["levels_completed"]
    if block == target:
        levels += 1
    return {
        "frame": frames,
        "state": "NOT_FINISHED",
        "levels_completed": levels,
        "available_actions": list(AVAIL),
    }
