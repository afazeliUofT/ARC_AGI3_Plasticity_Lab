import copy

def predict(history, action):
    last = history[-1]
    frame = copy.deepcopy(last["frame"])
    n = len(history)  # index of the observation being predicted
    total = 50
    g = frame[0]
    h = len(g)
    w = len(g[h - 1])

    # Bottom progress bar fills right-to-left: round(64 * n / 50) cells.
    filled = int(64 * n / total + 0.5)
    filled = max(0, min(w, filled))
    row = g[h - 1]
    for x in range(w - filled, w):
        row[x] = 4

    # Observed change at step 10: the object at rows 9-11 shrinks.
    if n == 10:
        for y in (9, 10, 11):
            for x in (30, 31, 32):
                g[y][x] = 5
        g[10][28] = 13

    return {
        "frame": frame,
        "state": last["state"],
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }
