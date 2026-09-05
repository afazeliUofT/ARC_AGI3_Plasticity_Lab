# GOAL: The level is completed when the 10x10 block (rows 34-43, cols 27-36) exactly matches the target picture (rows 3-12, cols 3-12); the cup sits on one of the 8 ring positions around the block (actions 1/2/3/4 move it up/down/left/right by one ring step and are ignored when the step would leave the ring, which is why a second "left" at the top-left corner did nothing), and a press (5) pushes the cup 7 cells toward the block and paints with the cup colour the block half (or corner triangle) on the cup's side, so moving the cup down the left side to the bottom and pressing purple paints the bottom half purple and yields the top-white/bottom-purple target.

BLOCK_R0, BLOCK_C0 = 34, 27
TARGET_R0, TARGET_C0 = 3, 3
AVAIL = [1, 2, 3, 4, 5, 6]

# base upright cup (orientation 0, above the block), absolute coords: (row, col, 'w' wall / 'l' liquid)
UP = []
for _c in range(25, 39):
    UP.append((24, _c, 'w'))
for _r in range(25, 32):
    UP.append((_r, 25, 'w'))
    UP.append((_r, 38, 'w'))
    for _c in range(26, 38):
        UP.append((_r, _c, 'l'))
UP.append((32, 25, 'w'))
UP.append((32, 38, 'w'))

# base diamond cup at upper-left (orientation 1), absolute coords
_DW = {21: [(24, 24)], 22: [(23, 25)], 23: [(22, 23), (25, 26)], 24: [(21, 22), (26, 27)],
       25: [(20, 21), (27, 28)], 26: [(19, 20), (28, 29)], 27: [(18, 19), (29, 30)],
       28: [(17, 18)], 29: [(16, 17)], 30: [(15, 16)], 31: [(14, 15)], 32: [(15, 16)],
       33: [(16, 17)], 34: [(17, 18)], 35: [(18, 19)], 36: [(19, 20)], 37: [(20, 20)]}
_DL = {23: (24, 24), 24: (23, 25), 25: (22, 26), 26: (21, 27), 27: (20, 28), 28: (19, 28),
       29: (18, 27), 30: (17, 26), 31: (16, 25), 32: (17, 24), 33: (18, 23), 34: (19, 22),
       35: (20, 21)}
DIA = []
for _r, _runs in _DW.items():
    for _a, _b in _runs:
        for _c in range(_a, _b + 1):
            DIA.append((_r, _c, 'w'))
for _r, (_a, _b) in _DL.items():
    for _c in range(_a, _b + 1):
        DIA.append((_r, _c, 'l'))

# direction the cup moves during a press, per orientation
DIRS = {0: (1, 0), 1: (1, 1), 2: (0, 1), 3: (-1, 1), 4: (-1, 0), 5: (-1, -1), 6: (0, -1), 7: (1, -1)}

# ring positions (dx, dy) around the block -> orientation index
POS_TO_N = {(0, -1): 0, (-1, -1): 1, (-1, 0): 2, (-1, 1): 3,
            (0, 1): 4, (1, 1): 5, (1, 0): 6, (1, -1): 7}
MOVES = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}


def _cells(n):
    base = UP if n % 2 == 0 else DIA
    out = []
    for r, c, k in base:
        if n == 0 or n == 1:
            rr, cc = r, c
        elif n == 2:
            rr, cc = 70 - c, r - 7
        elif n == 3 or n == 4:
            rr, cc = 77 - r, c
        elif n == 5:
            rr, cc = 77 - r, 63 - c
        elif n == 6:
            rr, cc = 70 - c, 70 - r
        else:
            rr, cc = r, 63 - c
        out.append((rr, cc, k))
    return out


def _in_mask(n, i, j):
    return [i <= 4, i + j <= 9, j <= 4, i >= j, i >= 5, i + j >= 9, j >= 5, j >= i][n]


def _stamp(block, n, color):
    return [[color if _in_mask(n, i, j) else block[i][j] for j in range(10)] for i in range(10)]


def _counter(cnt):
    return max(0, min(64, (128 * cnt + 100) // 200))


def _render(template, n, color, block, cnt, k):
    g = [row[:] for row in template[:18]] + [[5] * 64 for _ in range(45)]
    for x in range(35, 46):
        g[7][x] = 3
    xs = range(35, 40) if color == 0 else range(41, 46)
    for x in xs:
        g[7][x] = 0
    for i in range(10):
        for j in range(10):
            g[BLOCK_R0 + i][BLOCK_C0 + j] = block[i][j]
    dr, dc = DIRS[n]
    for (r, c, kind) in _cells(n):
        rr, cc = r + dr * k, c + dc * k
        if 18 <= rr <= 62 and 0 <= cc < 64:
            g[rr][cc] = 2 if kind == 'w' else color
    c = _counter(cnt)
    g.append([4] * (64 - c) + [5] * c)
    return g


def _step(template, pos, color, block, cnt, action):
    a = action.get("action")
    data = action.get("data") or {}
    cnt += 1
    frames = None
    if a in MOVES:
        dx, dy = MOVES[a]
        np_ = (pos[0] + dx, pos[1] + dy)
        if np_ in POS_TO_N:
            pos = np_
    elif a == 5:
        n = POS_TO_N[pos]
        new_block = _stamp(block, n, color)
        frames = []
        for t in range(15):
            k = t if t <= 7 else 14 - t
            blk = block if t <= 7 else new_block
            frames.append(_render(template, n, color, blk, cnt, k))
        block = new_block
    elif a == 6:
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            if 2 <= y <= 7 and 35 <= x <= 39:
                color = 0
            elif 2 <= y <= 7 and 41 <= x <= 45:
                color = 15
    if frames is None:
        frames = [_render(template, POS_TO_N[pos], color, block, cnt, 0)]
    return pos, color, block, cnt, frames


def predict(history, action):
    template = history[0]["frame"][0]
    pos, color, cnt = (0, -1), 15, 0
    block = [[template[BLOCK_R0 + i][BLOCK_C0 + j] for j in range(10)] for i in range(10)]
    for rec in history[1:]:
        a = rec.get("action")
        if a is None:
            continue
        pos, color, block, cnt, _ = _step(template, pos, color, block, cnt, a)
    pos, color, block, cnt, frames = _step(template, pos, color, block, cnt, action)
    target = [[template[TARGET_R0 + i][TARGET_C0 + j] for j in range(10)] for i in range(10)]
    levels = history[-1]["levels_completed"]
    state = "NOT_FINISHED"
    if block == target:
        levels += 1
        state = "NOT_FINISHED"
    return {
        "frame": frames,
        "state": state,
        "levels_completed": levels,
        "available_actions": list(AVAIL),
    }
