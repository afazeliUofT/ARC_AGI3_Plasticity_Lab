import copy

def _find_player(frame):
    cells = [(r, c) for r in range(63) for c in range(64) if frame[r][c] in (0, 14)]
    if not cells:
        return None
    return min(r for r, _ in cells), min(c for _, c in cells)

def predict(history, action):
    last = history[-1]
    frame = copy.deepcopy(last["frame"])
    g = frame[0]
    a = action.get("action", 5)

    pos = _find_player(g)
    if pos is not None and a in (1, 2, 3, 4):
        r0, c0 = pos
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                g[r][c] = 1
        dr, dc = {1: (-4, 0), 2: (4, 0), 3: (0, -4), 4: (0, 4)}[a]
        nr, nc = r0 + dr, c0 + dc
        ok = 0 <= nr and nr + 3 <= 62 and 0 <= nc and nc + 3 <= 63
        if ok:
            for r in range(nr, nr + 4):
                for c in range(nc, nc + 4):
                    if g[r][c] != 1:
                        ok = False
        if ok:
            r0, c0 = nr, nc
        for r in range(r0, r0 + 4):
            for c in range(c0, c0 + 4):
                g[r][c] = 14
        if a == 1:
            for c in range(c0, c0 + 4):
                g[r0][c] = 0
        elif a == 2:
            for c in range(c0, c0 + 4):
                g[r0 + 3][c] = 0
        elif a == 3:
            for r in range(r0, r0 + 4):
                g[r][c0] = 0
        else:
            for r in range(r0, r0 + 4):
                g[r][c0 + 3] = 0

    # bottom bar: tick model. Moves cost 2 ticks, waits (action 5) cost 1 tick,
    # 4 initial ticks; one bar cell (from the right) per 6 ticks.
    actions = []
    for h in history[1:]:
        act = h.get("action")
        if act is not None:
            actions.append(act.get("action", 5))
    actions.append(a)
    moves = sum(1 for x in actions if x in (1, 2, 3, 4))
    waits = len(actions) - moves
    ticks = 4 + 2 * moves + waits
    n = min(ticks // 6, 64)
    for c in range(64 - n, 64):
        g[63][c] = 4

    return {
        "frame": frame,
        "state": last["state"],
        "levels_completed": last["levels_completed"],
        "available_actions": list(last["available_actions"]),
    }
