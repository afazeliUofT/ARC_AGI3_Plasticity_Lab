import copy

def _draw_hbar(g, L):
    for y in (9, 10, 11):
        for x in range(28, 64):
            g[y][x] = 5
    g[9][52] = 13; g[11][52] = 13; g[10][51] = 13; g[10][53] = 13
    for y in (9, 10, 11):
        for x in range(28, min(64, 28 + L)):
            g[y][x] = 14
    if L >= 1:
        d = 27 + L - 1
        if 28 <= d < 64:
            g[10][d] = 13

def _draw_vbar(g, L):
    for y in range(28, 63):
        for x in (9, 10, 11):
            g[y][x] = 5
    g[51][10] = 13; g[53][10] = 13; g[52][9] = 13; g[52][11] = 13
    for y in range(28, min(63, 28 + L)):
        for x in (9, 10, 11):
            g[y][x] = 11
    if L >= 1:
        d = 27 + L - 1
        if 28 <= d < 63:
            g[d][10] = 13

def predict(history, action):
    last = history[-1]
    frame = copy.deepcopy(last["frame"])
    n = len(history)
    g = frame[0]
    h = len(g)
    w = len(g[0])
    state = last["state"]

    if state != "NOT_FINISHED":
        return {
            "frame": frame,
            "state": state,
            "levels_completed": last["levels_completed"],
            "available_actions": list(last["available_actions"]),
        }

    # current bar lengths
    hl = 0
    x = 28
    while x < 64 and g[9][x] == 14:
        hl += 1; x += 1
    vl = 0
    y = 28
    while y < 63 and g[y][9] == 11:
        vl += 1; y += 1

    data = action.get("data") or {}
    if action.get("action") == 6 and "x" in data and "y" in data:
        cx, cy = data["x"], data["y"]
        if 18 <= cy <= 24 and 36 <= cx <= 48:
            if cx < 42:
                hl = max(2, hl - 3)
            elif cx > 42:
                hl = min(36, hl + 3)
            _draw_hbar(g, hl)
        elif 35 <= cy <= 47 and 21 <= cx <= 27:
            if cy < 41:
                vl = max(2, vl - 3)
            elif cy > 41:
                vl = min(35, vl + 3)
            _draw_vbar(g, vl)

    # timer / progress bar on bottom row, filling from the right
    filled = int(64 * n / 50 + 0.5)
    filled = max(0, min(w, filled))
    row = g[h - 1]
    for x in range(w - filled, w):
        row[x] = 4

    if n >= 50:
        state = "GAME_OVER"

    return {
        "frame": frame,
        "state": state,
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }
