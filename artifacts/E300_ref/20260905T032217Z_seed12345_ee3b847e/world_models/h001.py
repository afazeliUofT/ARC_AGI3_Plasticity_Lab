import copy

def predict(history, action):
    prev = history[-1]
    frame = copy.deepcopy(prev["frame"])
    n = len(history)  # number of actions taken including this one
    consumed = int(64 * n / 50 + 0.5)
    if consumed > 64:
        consumed = 64
    row = frame[0][63]
    for x in range(64 - consumed, 64):
        row[x] = 4
    return {
        "frame": frame,
        "state": prev["state"],
        "levels_completed": prev["levels_completed"],
        "available_actions": list(prev["available_actions"]),
    }
