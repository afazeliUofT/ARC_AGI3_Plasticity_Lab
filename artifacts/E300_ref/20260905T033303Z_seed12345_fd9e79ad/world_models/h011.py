import copy

def _find_player(frame):
    cells = [(r, c) for r in range(63) for c in range(64) if frame[r][c] in (0, 14)]
    if not cells:
        return None
    return min(r for r, _ in cells), min(c for _, c in cells)

def _reset_obs(history):
    base = history[0]
    return {
        "frame": copy.deepcopy(base["frame"]),
        "state": "NOT_FINISHED",
        "levels_completed": base.get("levels_completed", 0),
        "available_actions": list(base["available_actions"]),
    }

def predict(history, action):
    last = history[-1]
    a = action.get("action", 5)

    # action 0 restarts the level from the reset observation
    if a == 0:
        return _reset_obs(history)

    frame = copy.deepcopy(last["frame"])
    g = frame[0]

    # once the game is over nothing changes any more (except reset)
    if last["state"] == "GAME_OVER":
        return {
            "frame": frame,
            "state": last["state"],
            "levels_completed": last["levels_completed"],
            "available_actions": list(last["available_actions"]),
        }

    pos = _find_player(g)
    if pos is not None and a in (1, 2, 3, 4):
        r0, c0 = pos
        # erase player
        for r in range(r0, min(r0 + 4, 63)):
            for c in range(c0, c0 + 4):
                g[r][c] = 1
        dr, dc = {1: (-4, 0), 2: (4, 0), 3: (0, -4), 4: (0, 4)}[a]
        nr, nc = r0 + dr, c0 + dc
        in_bounds = 0 <= nr and nr + 3 <= 63 and 0 <= nc and nc + 3 <= 63
        ok = in_bounds
        if in_bounds:
            for r in range(nr, min(nr + 4, 63)):
                for c in range(nc, nc + 4):
                    if g[r][c] != 1:
                        ok = False
        if ok:
            r0, c0 = nr, nc
        # draw player with facing strip
        for r in range(r0, min(r0 + 4, 63)):
            for c in range(c0, c0 + 4):
                g[r][c] = 14
        if a == 1:
            for c in range(c0, c0 + 4):
                g[r0][c] = 0
        elif a == 2:
            if r0 + 3 <= 62:
                for c in range(c0, c0 + 4):
                    g[r0 + 3][c] = 0
        elif a == 3:
            for r in range(r0, min(r0 + 4, 63)):
                g[r][c0] = 0
        else:
            for r in range(r0, min(r0 + 4, 63)):
                g[r][c0 + 3] = 0

        # un-highlight any previously highlighted block
        for r in range(63):
            row = g[r]
            for c in range(64):
                if row[c] == 3:
                    row[c] = 4
        # highlight the block directly in front of the player (facing direction)
        fr, fc = r0 + dr, c0 + dc
        for r in range(max(fr, 0), min(fr + 4, 63)):
            for c in range(max(fc, 0), min(fc + 4, 64)):
                if g[r][c] == 4:
                    g[r][c] = 3

    # step counter restarts at the most recent reset (action 0) or the start
    last_reset = 0
    for i in range(len(history) - 1, 0, -1):
        act = history[i].get("action")
        if act is not None and act.get("action") == 0:
            last_reset = i
            break
    used = (len(history) - 1 - last_reset) + 1
    n = (16 * used + 25) // 50  # round(64*used/200)
    n = max(0, min(64, n))
    for c in range(64):
        g[63][c] = 4 if c >= 64 - n else 7

    state = last["state"]
    if used >= 200:
        state = "GAME_OVER"

    return {
        "frame": frame,
        "state": state,
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }
