import copy

def _replay(history, action):
    len_h = 5   # horizontal creature (rows 9-11), tail at col 28
    len_v = 8   # vertical creature (cols 9-11), tail at row 28
    acts = [h["action"] for h in history[1:]] + [action]
    for a in acts:
        if a is None or a.get("action") != 6:
            continue
        d = a.get("data") or {}
        if "x" not in d or "y" not in d:
            continue
        x, y = d["x"], d["y"]
        if 19 <= y <= 23 and 37 <= x <= 41:
            len_h -= 3
        elif 19 <= y <= 23 and 43 <= x <= 47:
            len_h += 3
        elif 36 <= y <= 40 and 22 <= x <= 26:
            len_v -= 3
        elif 42 <= y <= 46 and 22 <= x <= 26:
            len_v += 3
        len_h = max(0, min(36, len_h))
        len_v = max(0, min(35, len_v))
    return len_h, len_v


def predict(history, action):
    prev = history[-1]
    frame = copy.deepcopy(history[0]["frame"])
    g = frame[0]
    len_h, len_v = _replay(history, action)

    # clear creature lanes
    for y in range(9, 12):
        for x in range(28, 64):
            g[y][x] = 5
    for y in range(28, 63):
        for x in range(9, 12):
            g[y][x] = 5
    # targets
    for (y, x) in [(9, 52), (10, 51), (10, 53), (11, 52),
                   (51, 10), (52, 9), (52, 11), (53, 10)]:
        g[y][x] = 13
    # horizontal creature: tail col 28, head col 28+len-1, eye at head-1
    for x in range(28, 28 + len_h):
        if 28 <= x <= 63:
            for y in range(9, 12):
                g[y][x] = 14
    ex = 28 + len_h - 2
    if len_h >= 2 and 28 <= ex <= 63:
        g[10][ex] = 13
    # vertical creature: tail row 28, head row 28+len-1, eye at head-1
    for y in range(28, 28 + len_v):
        if 28 <= y <= 62:
            for x in range(9, 12):
                g[y][x] = 11
    ey = 28 + len_v - 2
    if len_v >= 2 and 28 <= ey <= 62:
        g[ey][10] = 13

    # timer bar: fills from the right at 64/50 cells per action, rounded
    n = len(history)
    consumed = int(64 * n / 50 + 0.5)
    if consumed > 64:
        consumed = 64
    for x in range(64):
        g[63][x] = 3
    for x in range(64 - consumed, 64):
        g[63][x] = 4

    return {
        "frame": frame,
        "state": prev["state"],
        "levels_completed": prev["levels_completed"],
        "available_actions": list(prev["available_actions"]),
    }
