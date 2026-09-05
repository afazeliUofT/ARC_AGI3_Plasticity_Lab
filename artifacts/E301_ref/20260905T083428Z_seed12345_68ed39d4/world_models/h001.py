def _cup_cells(orient):
    cells = []
    if orient == 0:
        for c in range(25, 39):
            cells.append((24, c, 2))
        for r in range(25, 32):
            cells.append((r, 25, 2))
            for c in range(26, 38):
                cells.append((r, c, 15))
            cells.append((r, 38, 2))
        cells.append((32, 25, 2))
        cells.append((32, 38, 2))
        return cells
    tilt = {
        21: [(39, 39, 2)],
        22: [(38, 40, 2)],
        23: [(37, 38, 2), (39, 39, 15), (40, 41, 2)],
        24: [(36, 37, 2), (38, 40, 15), (41, 42, 2)],
        25: [(35, 36, 2), (37, 41, 15), (42, 43, 2)],
        26: [(34, 35, 2), (36, 42, 15), (43, 44, 2)],
        27: [(33, 34, 2), (35, 43, 15), (44, 45, 2)],
        28: [(35, 44, 15), (45, 46, 2)],
        29: [(36, 45, 15), (46, 47, 2)],
        30: [(37, 46, 15), (47, 48, 2)],
        31: [(38, 47, 15), (48, 49, 2)],
        32: [(39, 46, 15), (47, 48, 2)],
        33: [(40, 45, 15), (46, 47, 2)],
        34: [(41, 44, 15), (45, 46, 2)],
        35: [(42, 43, 15), (44, 45, 2)],
        36: [(43, 44, 2)],
        37: [(43, 43, 2)],
    }
    for r, runs in tilt.items():
        for a, b, v in runs:
            for c in range(a, b + 1):
                cc = c if orient == 1 else 63 - c
                cells.append((r, cc, v))
    return cells


def _render(top, orient, off, fill, used):
    g = [list(row) for row in top]
    for r in range(18, 63):
        g[r] = [5] * 64
    for r in range(34, 44):
        for c in range(27, 37):
            g[r][c] = 15 if (r, c) in fill else 0
    for r, c, v in _cup_cells(orient):
        rr = r + off
        if 0 <= rr < 63:
            g[rr][c] = v
    fours = int(round(64 * (100 - used) / 100.0))
    fours = max(0, min(64, fours))
    g[63] = [4] * fours + [5] * (64 - fours)
    return g


def predict(history, action):
    last_rec = history[-1]
    last = last_rec["frame"][-1]
    used = len(history)

    # orientation from the frame
    if last[24][25] == 2 and last[24][38] == 2:
        orient = 0
    elif last[21][39] == 2:
        orient = 1
    elif last[21][24] == 2:
        orient = -1
    else:
        orient = 0

    fill = set()
    for r in range(34, 44):
        for c in range(27, 37):
            if last[r][c] == 15:
                fill.add((r, c))

    a = action.get("action")
    frames = []
    if a == 4:
        orient = min(orient + 1, 1)
        frames = [_render(last, orient, 0, fill, used)]
    elif a == 3:
        orient = max(orient - 1, -1)
        frames = [_render(last, orient, 0, fill, used)]
    elif a == 5:
        cells = _cup_cells(orient)
        for d in list(range(0, 8)) + list(range(6, -1, -1)):
            if d == 7:
                for r, c, v in cells:
                    rr = r + d
                    if v == 15 and 34 <= rr <= 43 and 27 <= c <= 36:
                        fill.add((rr, c))
            frames.append(_render(last, orient, d, fill, used))
    else:
        frames = [_render(last, orient, 0, fill, used)]

    return {
        "frame": frames,
        "state": last_rec.get("state", "NOT_FINISHED"),
        "levels_completed": last_rec.get("levels_completed", 0),
        "available_actions": [1, 2, 3, 4, 5, 6],
    }
