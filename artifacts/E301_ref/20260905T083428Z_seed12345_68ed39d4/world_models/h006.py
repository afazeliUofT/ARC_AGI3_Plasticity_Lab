CONT_R = range(34, 44)
CONT_C = range(27, 37)


def _upright():
    cells = []
    for c in range(25, 39):
        cells.append((24, c, 2))
    for r in range(25, 33):
        cells.append((r, 25, 2))
        cells.append((r, 38, 2))
    for r in range(25, 32):
        for c in range(26, 38):
            cells.append((r, c, 15))
    return cells


def _diag_left():
    cells = []
    for r in range(18, 45):
        for c in range(0, 64):
            u = c - r
            v = c + r
            if -15 <= u <= 1 and 47 <= v <= 56:
                cells.append((r, c, 15))
            elif -15 <= u <= 1 and v == 57:
                continue
            elif -17 <= u <= 3 and 45 <= v <= 57:
                cells.append((r, c, 2))
    return cells


def _mirror(cells):
    return [(r, 63 - c, v) for r, c, v in cells]


def _vflip(cells):
    return [(77 - r, c, v) for r, c, v in cells]


def _transpose(cells):
    return [(c + 7, r - 7, v) for r, c, v in cells]


_U = _upright()
_L1 = _diag_left()
SPRITES = {
    (0, -1): _U,
    (-1, -1): _L1,
    (1, -1): _mirror(_L1),
    (-1, 0): _transpose(_U),
    (1, 0): _mirror(_transpose(_U)),
    (0, 1): _vflip(_U),
    (-1, 1): _vflip(_L1),
    (1, 1): _vflip(_mirror(_L1)),
}

MOVES = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}
TOTAL_ACTIONS = 100


def _move(pos, a):
    if a not in MOVES:
        return pos
    dx, dy = MOVES[a]
    nx, ny = pos[0] + dx, pos[1] + dy
    if (nx, ny) == (0, 0) or abs(nx) > 1 or abs(ny) > 1:
        return pos
    return (nx, ny)


def _bar(fours):
    fours = max(0, min(64, fours))
    return [4] * fours + [5] * (64 - fours)


def _render(base, pos, shift, fill, fours):
    g = [list(row) for row in base]
    while len(g) < 64:
        g.append([5] * 64)
    for r in range(18, 63):
        g[r] = [5] * 64
    for r in CONT_R:
        for c in CONT_C:
            g[r][c] = 15 if (r, c) in fill else 0
    dr, dc = -pos[1], -pos[0]
    for r, c, v in SPRITES[pos]:
        rr = r + dr * shift
        cc = c + dc * shift
        if 0 <= rr < 63 and 0 <= cc < 64:
            g[rr][cc] = v
    g[63] = _bar(fours)
    return g


def _detect(last):
    for pos, cells in SPRITES.items():
        ok = True
        for r, c, v in cells:
            if not (0 <= r < 64 and 0 <= c < 64) or last[r][c] != v:
                ok = False
                break
        if ok:
            return pos
    return None


def predict(history, action):
    last_rec = history[-1]
    last = last_rec["frame"][-1]
    used = len(history)
    avail = list(last_rec.get("available_actions", [1, 2, 3, 4, 5, 6]))
    levels = last_rec.get("levels_completed", 0)

    # Game already over: nothing changes.
    if last_rec.get("state") == "GAME_OVER":
        return {
            "frame": [[list(row) for row in last]],
            "state": "GAME_OVER",
            "levels_completed": levels,
            "available_actions": avail,
        }

    fours = int(round(64 * (TOTAL_ACTIONS - used) / 100.0))

    # Final action: budget exhausted, action is not applied, game ends.
    if used >= TOTAL_ACTIONS:
        g = [list(row) for row in last]
        while len(g) < 64:
            g.append([5] * 64)
        g[63] = _bar(fours)
        return {
            "frame": [g],
            "state": "GAME_OVER",
            "levels_completed": levels,
            "available_actions": avail,
        }

    pos = _detect(last)
    if pos is None:
        pos = (0, -1)
        for rec in history[1:]:
            act = rec.get("action") or {}
            pos = _move(pos, act.get("action"))

    fill = set()
    for r in CONT_R:
        for c in CONT_C:
            if last[r][c] == 15:
                fill.add((r, c))

    a = action.get("action")
    frames = []
    if a in (1, 2, 3, 4):
        pos = _move(pos, a)
        frames = [_render(last, pos, 0, fill, fours)]
    elif a == 5:
        dr, dc = -pos[1], -pos[0]
        shifts = list(range(0, 8)) + list(range(6, -1, -1))
        for idx, d in enumerate(shifts):
            if idx == 7:
                front = None
                for r, c, v in SPRITES[pos]:
                    if v == 15:
                        rr = r + dr * 7
                        cc = c + dc * 7
                        depth = rr * dr + cc * dc
                        if front is None or depth > front:
                            front = depth
                if front is not None:
                    for r in CONT_R:
                        for c in CONT_C:
                            if r * dr + c * dc <= front:
                                fill.add((r, c))
            frames.append(_render(last, pos, d, fill, fours))
    else:
        frames = [_render(last, pos, 0, fill, fours)]

    return {
        "frame": frames,
        "state": last_rec.get("state", "NOT_FINISHED"),
        "levels_completed": levels,
        "available_actions": avail,
    }
