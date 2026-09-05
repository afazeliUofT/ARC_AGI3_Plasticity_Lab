import copy

def predict(history, action):
    last = history[-1]
    frame = copy.deepcopy(last["frame"])
    n = len(history)  # number of actions taken including this one
    total = 50
    filled = int(64 * n / total + 0.5)
    filled = max(0, min(64, filled))
    g = frame[0]
    h = len(g)
    w = len(g[h - 1])
    row = g[h - 1]
    for x in range(w - filled, w):
        row[x] = 4
    return {
        "frame": frame,
        "state": last["state"],
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }
