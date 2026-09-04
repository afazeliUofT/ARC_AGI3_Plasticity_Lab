"""The sandbox worker process: ``python -m arc_plasticity.hypotheses.sandbox_worker``.

Spawned by :class:`arc_plasticity.hypotheses.sandbox.SandboxedProgram`; see that module for
the protocol and the guarantees. This module imports only the standard library and
``arc_plasticity.core.guards`` so that a worker never loads the toolkit, numpy or any
project data. Every limit arrives in the ``load`` request; nothing numeric is defined here.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any


class PredictTimeout(Exception):
    """Raised by the worker's SIGALRM handler inside the program's ``predict``."""


class FilesystemForbiddenError(PermissionError):
    """The program tried a forbidden file operation."""


def install_file_guard(repository_root: str, forbidden_read_roots: Sequence[str]) -> None:
    """Best-effort in-process guard over the common file entry points.

    Writes under ``repository_root`` and any access under ``forbidden_read_roots`` raise
    :class:`FilesystemForbiddenError`. Imports are unaffected (they use ``io.open_code``).
    """
    import builtins
    import io

    repo = os.path.realpath(repository_root)
    forbidden = [os.path.realpath(p) for p in forbidden_read_roots]

    def under(path: str, root: str) -> bool:
        return path == root or path.startswith(root + os.sep)

    def check(path_like: Any, writing: bool) -> None:
        if isinstance(path_like, int):
            return
        try:
            path = os.path.realpath(os.fspath(path_like))
        except TypeError:
            return
        if writing and under(path, repo):
            raise FilesystemForbiddenError(f"write under the repository refused: {path}")
        for root in forbidden:
            if under(path, root):
                raise FilesystemForbiddenError(f"access to {root} refused: {path}")

    original_open = builtins.open

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        check(file, any(ch in mode for ch in "wax+"))
        return original_open(file, mode, *args, **kwargs)

    builtins.open = guarded_open  # type: ignore[assignment]
    io.open = guarded_open  # type: ignore[assignment]

    original_os_open = os.open
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        check(path, bool(flags & write_flags))
        return original_os_open(path, flags, *args, **kwargs)

    os.open = guarded_os_open  # type: ignore[assignment]

    for name in (
        "remove",
        "unlink",
        "rmdir",
        "mkdir",
        "truncate",
        "chmod",
        "utime",
        "rename",
        "replace",
        "link",
        "symlink",
    ):
        original = getattr(os, name)

        def guarded(*args: Any, _original: Any = original, **kwargs: Any) -> Any:
            for arg in args[:2]:
                check(arg, True)
            return _original(*args, **kwargs)

        setattr(os, name, guarded)


def classify(exc: BaseException) -> str:
    from arc_plasticity.core.guards import NetworkForbiddenError

    if isinstance(exc, PredictTimeout):
        return "predict_timeout"
    if isinstance(exc, MemoryError):
        return "memory"
    if isinstance(exc, NetworkForbiddenError):
        return "network"
    if isinstance(exc, FilesystemForbiddenError):
        return "filesystem"
    return "raised"


def main() -> int:
    import resource
    import signal
    import traceback

    from arc_plasticity.core.guards import NetworkGuard

    # The protocol owns the original stdout; program prints go to stderr.
    protocol_out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    protocol_in = os.fdopen(0, "rb")

    def send(obj: Mapping[str, Any]) -> None:
        protocol_out.write(json.dumps(obj, separators=(",", ":")).encode("utf-8") + b"\n")
        protocol_out.flush()

    def on_alarm(signum: int, frame: object) -> None:
        raise PredictTimeout()

    load_line = protocol_in.readline()
    if not load_line:
        return 1
    load = json.loads(load_line)
    if load.get("op") != "load":
        send({"ok": False, "kind": "protocol", "message": "first request must be load"})
        return 1
    limits = load["limits"]
    address_space = int(limits["address_space_bytes_max"])
    predict_seconds = float(limits["predict_seconds_max"])
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    NetworkGuard(allowed_calls=0).__enter__()
    guards = load["guards"]
    install_file_guard(guards["repository_root"], guards["forbidden_read_roots"])
    signal.signal(signal.SIGALRM, on_alarm)

    namespace: dict[str, Any] = {"__name__": "candidate_program", "__file__": "<candidate>"}
    try:
        exec(compile(load["source"], "<candidate>", "exec"), namespace)  # noqa: S102
        predict = namespace["predict"]
        if not callable(predict):
            raise TypeError("predict is not callable")
    except BaseException as exc:  # noqa: BLE001 - untrusted code; every failure is reported
        kind = classify(exc)
        send(
            {
                "ok": False,
                "kind": "load_failed" if kind == "raised" else kind,
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-2000:],
            }
        )
        return 1
    send({"ok": True})

    history: list[dict[str, Any]] = []
    while True:
        line = protocol_in.readline()
        if not line:
            return 0
        request = json.loads(line)
        op = request.get("op")
        if op == "set_history":
            history = list(request["history"])
            send({"ok": True, "history_length": len(history) - 1})
        elif op == "extend":
            history.append(request["transition"])
            send({"ok": True, "history_length": len(history) - 1})
        elif op == "predict":
            signal.setitimer(signal.ITIMER_REAL, predict_seconds)
            try:
                # A shallow copy: a program that mutates the records only corrupts its own
                # later inputs; certification compares against the parent's history.
                result = predict(list(history), dict(request["action"]))
                signal.setitimer(signal.ITIMER_REAL, 0)
                send({"ok": True, "prediction": result})
            except BaseException as exc:  # noqa: BLE001 - untrusted code; reported by kind
                signal.setitimer(signal.ITIMER_REAL, 0)
                send(
                    {
                        "ok": False,
                        "kind": classify(exc),
                        "message": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc()[-2000:],
                    }
                )
        elif op == "exit":
            return 0
        else:
            send({"ok": False, "kind": "protocol", "message": f"unknown op {op!r}"})


if __name__ == "__main__":
    sys.exit(main())
