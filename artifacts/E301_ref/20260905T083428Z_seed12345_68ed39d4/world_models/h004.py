CONT_R = range(34, 44)
CONT_C = range(27, 37)
DIRS = {0: (1, 0), -1: (1, 1), 1: (1, -1), -2: (0, 1), 2: (0, -1)}
ORIENTS = [0, -1, 1, -2, 2]


def _sprite(orient):
    cells = []
    if orient == 0:
        for c in range(25, 39):
            cells.append((24, c, 2))
        for r in range(25, 33):
            cells.append((r, 25, 2))
            cells.append((r, 38, 2))
        for r in range(25, 32):
            for c in range(26, 38):
                cells.append((r, c, 15))
        return cells
    if abs(orient) == 1:
        for r in range(18, 46):
            for c in range(0, 64):
                u = c - r
                v = c + r
                if -15 <= u <= 1 and 47 <= v <= 56:
                    cells.append((r, c, 15))
                elif -15 <= u <= 1 and v == 57:
                    continue
                elif -17 <= u <= 3 and 45 <= v <= 57:
                    cells.append((r, c, 2))
        if orient == 1:
            cells = [(r, 63 - c, v) for r, c, v in cells]
        return cells
    for c in range(17, 26):
        cells.append((32, c, 2))
        cells.append((45, c, 2))
    for r in range(33, 45):
        cells.append((r, 17, 2))
        for c in range(18, 25):
            cells.append((r, c, 15))
    if orient == 2:
        cells = [(r, 63 - c, v) for r, c, v in cells]
    return cells


SPRITES = {o: _sprite(o) for o in ORIENTS}


def _render(base, orient, shift, fill, fours):
    g = [list(row) for row in base]
    for r in range(18, 63):
        g[r] = [5] * 64
    for r in CONT_R:
        for c in CONT_C:
            g[r][c] = 15 if (r, c) in fill else 0
    dr, dc = DIRS[orient]
    for r, c, v in SPRITES[orient]:
        rr = r + dr * shift
        cc = c + dc * shift
        if 0 <= rr < 63 and 0 <= cc < 64:
            g[rr][cc] = v
    fours = max(0, min(64, fours))
    g[63] = [4] * fours + [5] * (64 - fours)
    return g


def _rotate(orient, a):
    if a in (1, 4):
        return min(orient + 1, 2)
    if a in (2, 3):
        return max(orient - 1, -2)
    return orient


def _detect_orient(last):
    for o in ORIENTS:
        ok = True
        for r, c, v in SPRITES[o]:
            if v == 2 and last[r][c] != 2:
                ok = False
                break
        if ok:
            return o
    return None


def predict(history, action):
    last_rec = history[-1]
    last = last_rec["frame"][-1]
    used = len(history)

    orient = _detect_orient(last)
    if orient is None:
        orient = 0
        for rec in history[1:]:
            act = rec.get("action") or {}
            orient = _rotate(orient, act.get("action"))

    fill = set()
    for r in CONT_R:
        for c in CONT_C:
            if last[r][c] == 15:
                fill.add((r, c))

    fours = int(round(64 * (100 - used) / 100.0))
    a = action.get("action")
    frames = []
    if a in (1, 2, 3, 4):
        orient = _rotate(orient, a)
        frames = [_render(last, orient, 0, fill, fours)]
    elif a == 5:
        dr, dc = DIRS[orient]
        for d in list(range(0, 8)) + list(range(6, -1, -1)):
            if d == 7:
                front = None
                for r, c, v in SPRITES[orient]:
                    if v == 15:
                        rr = r + dr * 7
                        cc = c + dc * 7
                        depth = rr * dr + cc * dc
                        if front is None or depth > front:
                            front = depth
                for r in CONT_R:
                    for c in CONT_C:
                        if r * dr + c * dc <= front:
                            fill.add((r, c))
            frames.append(_render(last, orient, d, fill, fours))
    else:
        frames = [_render(last, orient, 0, fill, fours)]

    return {
        "frame": frames,
        "state": last_rec.get("state", "NOT_FINISHED"),
        "levels_completed": last_rec.get("levels_completed", 0),
        "available_actions": list(last_rec.get("available_actions", [1, 2, 3, 4, 5, 6])),
    }
