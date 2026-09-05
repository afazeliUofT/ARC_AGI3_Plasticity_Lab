# GOAL: The level is completed when the 10x10 canvas block (rows 34-43, cols 27-36) exactly matches the target picture in the top-left panel (rows 3-12, cols 3-12), i.e. its top five rows are colour 0 and its bottom five rows are colour 15; a pour inserts five rows of the cup's colour at the top of the block and pushes the existing rows down, so selecting colour 0 in the palette (action 6 on the left box) and pouring (action 5) completes it.

BLOCK_R0, BLOCK_C0 = 34, 27
TARGET_R0, TARGET_C0 = 3, 3
CUP_TOP = 24
AVAIL = [1, 2, 3, 4, 5, 6]

# 45-degree clockwise rotated cup as observed (row -> runs of (c0, c1, kind))
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


def _push(block, color, n):
    if n <= 0:
        return [row[:] for row in block]
    n = min(n, 10)
    return [[color] * 10 for _ in range(n)] + [row[:] for row in block[:10 - n]]


def _cup_cells_r0(color, y0):
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


def _diamond_cells(color, dy):
    cells = []
    for row, runs in DIAMOND.items():
        for c0, c1, kind in runs:
            v = 2 if kind == 'w' else color
            for x in range(c0, c1 + 1):
                cells.append((row + dy, x, v))
    return cells


def _cup_cells(r, color, y0):
    r = r % 8
    if r == 0:
        return _cup_cells_r0(color, y0)
    if r == 1:
        return _diamond_cells(color, y0 - CUP_TOP)
    if r % 2 == 0:
        cells = _cup_cells_r0(color, y0)
        cy, cx = 28 + (y0 - CUP_TOP), 31
        for _ in range(r // 2):
            cells = [(cy + (x - cx), cx - (y - cy), v) for (y, x, v) in cells]
        return cells
    # odd rotations 3,5,7: flips of the observed diamond
    cells = _diamond_cells(color, y0 - CUP_TOP)
    if r in (3, 5):
        cells = [(58 - y + 2 * (y0 - CUP_TOP), x, v) for (y, x, v) in cells]
    if r in (5, 7):
        cells = [(y, 82 - x, v) for (y, x, v) in cells]
    return cells


def _render(template, r, color, block, counter, cup_row=CUP_TOP):
    g = [row[:] for row in template]
    for y in range(18, 63):
        g[y] = [5] * 64
    for i in range(10):
        for j in range(10):
            g[BLOCK_R0 + i][BLOCK_C0 + j] = block[i][j]
    for (y, x, v) in _cup_cells(r, color, cup_row):
        if 18 <= y < 63 and 0 <= x < 64:
            g[y][x] = v
    for x in range(35, 46):
        g[7][x] = 3
    xs = range(35, 40) if color == 0 else range(41, 46)
    for x in xs:
        g[7][x] = 0
    c = max(0, min(64, counter))
    g[63] = [4] * (64 - c) + [5] * c
    return g


def _step(template, r, color, block, counter, action):
    """Apply one action; returns (r, color, block, counter, frames)."""
    a = action.get("action")
    data = action.get("data") or {}
    frames = None
    if a == 4:
        r = (r + 1) % 8
        counter += 1
    elif a == 3:
        r = (r - 1) % 8
    elif a == 5:
        counter += 1
        if r % 8 == 0:
            frames = []
            for k in range(15):
                cup_row = CUP_TOP + k if k <= 7 else CUP_TOP + (14 - k)
                o = min(5, max(0, k - 2))
                blk = _push(block, color, o)
                frames.append(_render(template, r, color, blk, counter, cup_row))
            block = _push(block, color, 5)
    elif a == 6:
        counter += 1
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            if 3 <= y <= 5 and 36 <= x <= 38:
                color = 0
            elif 3 <= y <= 5 and 42 <= x <= 44:
                color = 15
    else:  # actions 1, 2 and anything unknown: no visible effect
        counter += 1
    if frames is None:
        frames = [_render(template, r, color, block, counter)]
    return r, color, block, counter, frames


def _target(template):
    return [[template[TARGET_R0 + i][TARGET_C0 + j] for j in range(10)] for i in range(10)]


def predict(history, action):
    template = history[0]["frame"][0]
    r, color, counter = 0, 15, 0
    block = [[0] * 10 for _ in range(10)]
    for rec in history[1:]:
        a = rec.get("action")
        if a is None:
            continue
        r, color, block, counter, _ = _step(template, r, color, block, counter, a)
    prev_block = block
    r, color, block, counter, frames = _step(template, r, color, block, counter, action)
    target = _target(template)
    levels = history[-1]["levels_completed"]
    if block == target and prev_block != target:
        levels += 1
    return {
        "frame": frames,
        "state": "NOT_FINISHED",
        "levels_completed": levels,
        "available_actions": list(AVAIL),
    }
