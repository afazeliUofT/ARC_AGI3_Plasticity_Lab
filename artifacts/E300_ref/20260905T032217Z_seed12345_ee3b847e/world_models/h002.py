import copy

LEN = 8      # creature length
EYE = 6      # eye offset from tail

def _replay(history, action):
    tail14 = 25  # horizontal creature (rows 9-11), tail column
    tail11 = 28  # vertical creature (cols 9-11), tail row
    acts = [h["action"] for h in history[1:]] + [action]
    for a in acts:
        if a is None or a.get("action") != 6:
            continue
        d = a.get("data") or {}
        if "x" not in d or "y" not in d:
            continue
        x, y = d["x"], d["y"]
        if 19 <= y <= 23 and 37 <= x <= 41:
            tail14 -= 3
        elif 19 <= y <= 23 and 43 <= x <= 47:
            tail14 += 3
        elif 36 <= y <= 40 and 22 <= x <= 26:
            tail11 -= 3
        elif 42 <= y <= 46 and 22 <= x <= 26:
            tail11 += 3
    return tail14, tail11

def predict(history, action):
    prev = history[-1]
    frame = copy.deepcopy(history[0]["frame"])
    g = frame[0]
    tail14, tail11 = _replay(history, action)

    # clear creature lanes
    for y in range(9, 12):
        for x in range(28, 64):
            g[y][x] = 5
    for y in range(28, 64):
        for x in range(9, 12):
            g[y][x] = 5
    # targets
    for (y, x) in [(9, 52), (10, 51), (10, 53), (51, 10), (52, 9), (52, 11)]:
        g[y][x] = 13
    # horizontal creature
    for x in range(tail14, tail14 + LEN):
        if 28 <= x <= 63:
            for y in range(9, 12):
                g[y][x] = 14
    ex = tail14 + EYE
    if 28 <= ex <= 63:
        g[10][ex] = 13
    # vertical creature
    for y in range(tail11, tail11 + LEN):
        if 28 <= y <= 63:
            for x in range(9, 12):
                g[y][x] = 11
    ey = tail11 + EYE
    if 28 <= ey <= 63:
        g[ey][10] = 13

    # timer bar
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
