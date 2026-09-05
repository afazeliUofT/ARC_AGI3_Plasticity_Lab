import copy


def _replay(history, action):
    len_h, len_v = 5, 8
    n = 0
    over = False
    acts = [h["action"] for h in history[1:]] + [action]
    for a in acts:
        if a is None:
            continue
        kind = a.get("action")
        if kind == 0:
            len_h, len_v, n, over = 5, 8, 0, False
            continue
        if over:
            continue
        if kind == 6:
            d = a.get("data") or {}
            x = d.get("x")
            y = d.get("y")
            if x is not None and y is not None:
                if 18 <= y <= 24 and 36 <= x <= 41:
                    len_h -= 3
                elif 18 <= y <= 24 and 43 <= x <= 48:
                    len_h += 3
                elif 21 <= x <= 27 and 35 <= y <= 40:
                    len_v -= 3
                elif 21 <= x <= 27 and 42 <= y <= 47:
                    len_v += 3
                len_h = max(0, min(36, len_h))
                len_v = max(0, min(35, len_v))
        n += 1
        if n >= 50:
            over = True
    return len_h, len_v, n, over


def predict(history, action):
    frame = copy.deepcopy(history[0]["frame"])
    g = frame[0]
    len_h, len_v, n, over = _replay(history, action)

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
    # horizontal creature
    for x in range(28, min(64, 28 + len_h)):
        for y in range(9, 12):
            g[y][x] = 14
    ex = 28 + len_h - 2
    if len_h >= 2 and ex <= 63:
        g[10][ex] = 13
    # vertical creature
    for y in range(28, min(63, 28 + len_v)):
        for x in range(9, 12):
            g[y][x] = 11
    ey = 28 + len_v - 2
    if len_v >= 2 and ey <= 62:
        g[ey][10] = 13

    # timer bar
    consumed = int(64 * n / 50 + 0.5)
    consumed = max(0, min(64, consumed))
    for x in range(64):
        g[63][x] = 3
    for x in range(64 - consumed, 64):
        g[63][x] = 4

    state = "GAME_OVER" if over else "NOT_FINISHED"
    return {
        "frame": frame,
        "state": state,
        "levels_completed": 0,
        "available_actions": [6],
    }
