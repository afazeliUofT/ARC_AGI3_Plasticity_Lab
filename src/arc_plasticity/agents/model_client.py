"""The language-model channel of the reference architecture (preregistration/G3.yaml
``model_calls``).

Two clients share one interface, :class:`ModelClient`:

* :class:`RecordedResponseClient` replays canned responses from a JSON file in order and
  refuses (:class:`ResponsesExhausted`) once they are used up. Holding the responses fixed
  makes the E300 runner a deterministic function of the experiment seed, which is what
  ``model_calls.nondeterminism_protocol`` asks ``tests/unit`` to assert. It makes no
  process, no network call and reads nothing but its file.
* :class:`HeadlessCliClient` (``kind`` ``headless_cli``, G3.5) runs one ``claude -p``
  subprocess per call: a fresh session (no ``--continue``, ``--no-session-persistence``),
  ``--output-format json``, ``--model`` and ``--effort`` from the request, every tool
  disabled (``--tools ""`` plus ``--permission-prompts none`` so nothing can prompt), the
  prompt on stdin, cwd a fresh temporary directory outside the repository (removed after),
  and an environment with every ``ARC_*`` variable and the nested-session markers removed.
  The JSON result is parsed into a :class:`ModelResponse`; a non-zero exit, a timeout or an
  ``is_error`` result is still a made call (recorded, no program). Only an authentication or
  usage-limit signature is a refusal (:class:`ModelClientError`), because such a call reached
  no model and the runner then marks the model unavailable rather than burning its budget.

  Credential (the human's answers of 2026-09-04, ``state/escalations/20260904T211800Z.md``
  and ``20260904T214700Z.md``): the child receives ``CLAUDE_CODE_OAUTH_TOKEN`` and nothing
  else. Claude Code strips that one variable from the environment of its own tool
  subprocesses, so a runner started inside a turn never has it; the supervisor therefore
  carries the same value under the alias :data:`TOKEN_ALIAS_ENV_KEY`
  (``PLASTICITY_LAB_OAUTH_TOKEN``, route (a) of the second answer). The adapter maps the alias
  to ``CLAUDE_CODE_OAUTH_TOKEN`` **in its child's environment only**, never re-exports the
  alias into that child or any other process, and never records either value. If neither
  variable is present at call time the call is refused **before any process starts**
  (:class:`CallRefused`, reason ``authentication_unavailable``); the adapter never attempts a
  login. Neither value is ever logged, placed in an artifact, a prompt, a ledger entry or an
  error message, and the alias *name* is kept out of artifacts too (``token_source`` records
  ``environment_alias`` instead). The ``token_file`` parameter (a file outside the
  repository) is declined for configs by :func:`build_client`, kept only for the unit test
  that pins secret handling, and is untested against the real binary.

Every call is described by a :class:`ModelRequest` and answered by a :class:`ModelResponse`
whose fields are exactly what ``model_calls.jsonl`` records: model as sent and as reported,
effort, cwd, ``tools_disabled``, the verbatim usage mapping, wall-clock and exit code. The
digest of this file (:func:`model_client_sha256`) goes into every E300 ``results.json``.
This module defines no threshold.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

PURPOSES: tuple[str, ...] = ("induce", "revise", "other")
CLIENT_KINDS: tuple[str, ...] = ("none", "recorded", "headless_cli")

# The usage keys the headless CLI reports, mapped to the four kinds the pre-registration
# sums (``tokens_by_kind``). A missing key counts as zero; the verbatim mapping is kept too.
USAGE_KEYS: dict[str, str] = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_creation": "cache_creation_input_tokens",
    "cache_read": "cache_read_input_tokens",
}

_FENCE_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)

# Headless CLI adapter constants (preregistration/G3.yaml model_calls.channel).
DEFAULT_EXECUTABLE = "claude"
DEFAULT_CALL_WALLCLOCK_SECONDS = 600
STDERR_TAIL_CHARS = 4000
STDOUT_TAIL_CHARS = 20000
EXIT_CODE_TIMED_OUT = -1
EXIT_CODE_NOT_STARTED = -2
# Environment keys never passed to the child: the benchmark key (leak_controls) and the
# markers a Claude Code session sets for its own children (a nested CLI refuses to start).
STRIPPED_ENV_PREFIXES: tuple[str, ...] = ("ARC_",)
STRIPPED_ENV_KEYS: tuple[str, ...] = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
TOKEN_ENV_KEY = "CLAUDE_CODE_OAUTH_TOKEN"
# The supervisor's alias for the same value (human's answer 2026-09-04T21:47Z, route (a)),
# chosen because the CLI strips TOKEN_ENV_KEY from its tool subprocesses and passes every
# other key through. Read by the adapter only; mapped to TOKEN_ENV_KEY in the child; never
# forwarded under its own name.
TOKEN_ALIAS_ENV_KEY = "PLASTICITY_LAB_OAUTH_TOKEN"
TOKEN_SOURCES: tuple[str, ...] = ("none", "environment", "environment_alias", "file")
# Refusal reasons of CallRefused. The first two come from a failed process; the third is
# raised before any process starts, when the credential variable is absent.
REFUSAL_AUTH = "auth"
REFUSAL_USAGE_LIMIT = "usage_limit"
REFUSAL_AUTHENTICATION_UNAVAILABLE = "authentication_unavailable"
# Signatures classifying a failed call as a refusal (no model was reached). Substrings,
# case-insensitive, matched against stderr and the result text. The usage-limit wording is the
# one docs/EVIDENCE_TOOLING.md section 7 and the supervisor's captured payloads record.
AUTH_SIGNATURES: tuple[str, ...] = (
    "not logged in",
    "login expired",
    "please run /login",
    "invalid api key",
    "authentication_error",
    "oauth token",
    "not authenticated",
)
USAGE_LIMIT_SIGNATURES: tuple[str, ...] = (
    "hit your session limit",
    "hit your weekly limit",
    "spend limit",
    "rate_limit_error",
    "usage limit",
)


class ModelClientError(RuntimeError):
    """A call could not be made at all (no client, no credential, no response left)."""


class ResponsesExhausted(ModelClientError):
    """The recorded response file has no response left for this call."""


class CallRefused(ModelClientError):
    """The headless CLI reached no model: authentication or usage-limit failure, or no
    credential variable at call time (``authentication_unavailable``, nothing spawned)."""

    def __init__(self, reason: str, message: str, raw: Mapping[str, Any]) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.raw = raw


@dataclass(frozen=True)
class ModelRequest:
    """``wallclock_seconds_max`` (optional) tightens the client's per-call limit for this one
    call, so a run-level wall-clock cap (the human's spend control) bounds the last call too."""

    call_index: int
    purpose: str
    prompt: str
    model_identifier: str
    effort: str
    wallclock_seconds_max: float | None = None

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise ValueError(f"purpose {self.purpose!r} not in {PURPOSES}")
        if self.call_index < 1:
            raise ValueError("call_index is 1-based")
        if self.wallclock_seconds_max is not None and self.wallclock_seconds_max <= 0:
            raise ValueError("wallclock_seconds_max must be positive when given")

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelResponse:
    """One answered call. ``raw`` is the response object exactly as the channel produced it."""

    text: str
    model_reported: str | None
    usage: Mapping[str, Any]
    raw: Mapping[str, Any]
    exit_code: int
    wallclock_seconds: float
    cwd: str
    tools_disabled: bool
    extra: Mapping[str, Any] = field(default_factory=dict)

    def tokens_by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for kind, key in USAGE_KEYS.items():
            value = self.usage.get(key, 0)
            out[kind] = (
                int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0
            )
        return out

    def tokens_total(self) -> int:
        return sum(self.tokens_by_kind().values())

    @property
    def response_sha256(self) -> str:
        return hashlib.sha256(canonical_response_text(self.raw).encode("utf-8")).hexdigest()


def canonical_response_text(raw: Mapping[str, Any]) -> str:
    """The bytes written to ``model_calls/<n>.response.json``: canonical JSON of ``raw``."""
    return json.dumps(dict(raw), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


@runtime_checkable
class ModelClient(Protocol):
    kind: str

    def call(self, request: ModelRequest) -> ModelResponse: ...

    def close(self) -> None: ...


def extract_program_source(text: str) -> str:
    """The candidate program in a model response: the first fenced Python block, or the
    whole text when there is no fence. Trailing whitespace is normalised to one newline."""
    match = _FENCE_RE.search(text)
    body = match.group(1) if match else text
    return body.rstrip() + "\n"


class RecordedResponseClient:
    """Replays ``responses[i]`` of a JSON file for the i-th call, then refuses.

    File shape: ``{"schema_version": 1, "responses": [{"text": str, "usage": {..},
    "model": str | null, "exit_code": int}, ...]}``. Each call is answered from a fresh
    temporary directory outside the repository (recorded as ``cwd`` and removed again) so the
    record has the same shape as a headless call's.
    """

    kind = "recorded"

    def __init__(self, responses_path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.responses_path = Path(responses_path)
        if not self.responses_path.is_file():
            raise ModelClientError(f"recorded responses file {self.responses_path} does not exist")
        doc = json.loads(self.responses_path.read_text(encoding="utf-8"))
        responses = doc.get("responses") if isinstance(doc, dict) else None
        if not isinstance(responses, list):
            raise ModelClientError(f"{self.responses_path} lacks a responses list")
        for i, item in enumerate(responses):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ModelClientError(f"{self.responses_path} responses[{i}] lacks a text string")
        self.responses: list[dict[str, Any]] = [dict(r) for r in responses]
        self.responses_sha256 = hashlib.sha256(self.responses_path.read_bytes()).hexdigest()
        self.calls_made = 0
        self._clock = clock

    @property
    def remaining(self) -> int:
        return len(self.responses) - self.calls_made

    def call(self, request: ModelRequest) -> ModelResponse:
        if self.calls_made >= len(self.responses):
            raise ResponsesExhausted(
                f"recorded responses exhausted after {self.calls_made} call(s) "
                f"({self.responses_path.name}); call {request.call_index} refused"
            )
        started = self._clock()
        item = self.responses[self.calls_made]
        self.calls_made += 1
        cwd = tempfile.mkdtemp(prefix="arc_model_stub_")
        try:
            usage_raw = item.get("usage")
            usage: dict[str, Any] = dict(usage_raw) if isinstance(usage_raw, dict) else {}
            raw = {
                "recorded": True,
                "responses_sha256": self.responses_sha256,
                "response_index": self.calls_made - 1,
                "model": item.get("model"),
                "result": item["text"],
                "usage": usage,
                "total_cost_usd": item.get("total_cost_usd"),
            }
            return ModelResponse(
                text=str(item["text"]),
                model_reported=item.get("model"),
                usage=usage,
                raw=raw,
                exit_code=int(item.get("exit_code", 0)),
                wallclock_seconds=self._clock() - started,
                cwd=cwd,
                tools_disabled=True,
            )
        finally:
            shutil.rmtree(cwd, ignore_errors=True)

    def close(self) -> None:
        return None


def _tail(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[-limit:]


def child_environment(
    parent: Mapping[str, str], token: str | None
) -> tuple[dict[str, str], list[str]]:
    """The environment a headless call receives: ``parent`` minus every stripped key and
    minus the alias :data:`TOKEN_ALIAS_ENV_KEY`, plus :data:`TOKEN_ENV_KEY` set from, in
    order of precedence, ``token`` (read from a file), the parent's own ``TOKEN_ENV_KEY``, or
    the parent's alias value. Returns the environment and the sorted list of keys removed
    (recorded per call; values never are). The alias is not listed among the removed keys so
    that its name reaches no artifact; :attr:`HeadlessCliClient.token_source` says where the
    credential came from."""
    env: dict[str, str] = {}
    stripped: list[str] = []
    for key, value in parent.items():
        if key == TOKEN_ALIAS_ENV_KEY:
            continue
        if key in STRIPPED_ENV_KEYS or key.startswith(STRIPPED_ENV_PREFIXES):
            stripped.append(key)
        else:
            env[key] = value
    if token is not None:
        env[TOKEN_ENV_KEY] = token
    elif not env.get(TOKEN_ENV_KEY) and parent.get(TOKEN_ALIAS_ENV_KEY):
        env[TOKEN_ENV_KEY] = parent[TOKEN_ALIAS_ENV_KEY]
    return env, sorted(stripped)


def token_source_of(parent: Mapping[str, str], token_from_file: bool) -> str:
    """Which of :data:`TOKEN_SOURCES` the child's credential comes from."""
    if token_from_file:
        return "file"
    if parent.get(TOKEN_ENV_KEY):
        return "environment"
    if parent.get(TOKEN_ALIAS_ENV_KEY):
        return "environment_alias"
    return "none"


def classify_refusal(exit_code: int, texts: Sequence[str]) -> str | None:
    """``auth`` or ``usage_limit`` when the failure signatures match, else ``None``.
    A call that exited 0 with a plain result is never a refusal."""
    joined = "\n".join(t for t in texts if t).lower()
    if not joined:
        return None
    if any(sig in joined for sig in AUTH_SIGNATURES):
        return REFUSAL_AUTH
    if any(sig in joined for sig in USAGE_LIMIT_SIGNATURES):
        return REFUSAL_USAGE_LIMIT
    return None


def headless_argv(executable: str, model_identifier: str, effort: str) -> list[str]:
    """The fixed argument vector (the prompt travels on stdin). Every flag is documented in
    docs/EVIDENCE_TOOLING.md section 2 or printed by ``claude --help`` 2.1.260."""
    return [
        executable,
        "-p",
        "--output-format",
        "json",
        "--model",
        model_identifier,
        "--effort",
        effort,
        "--tools",
        "",
        "--permission-prompts",
        "none",
        "--no-session-persistence",
    ]


class HeadlessCliClient:
    """One ``claude -p`` subprocess per call. See the module docstring.

    The credential is ``CLAUDE_CODE_OAUTH_TOKEN`` forwarded from ``environment`` (default: this
    process's own) or, when that variable is absent, the same value read from the supervisor's
    alias :data:`TOKEN_ALIAS_ENV_KEY` and placed under ``CLAUDE_CODE_OAUTH_TOKEN`` in the child
    only (``token_source`` ``environment_alias``); a call with neither is refused before
    anything is spawned.
    ``token_file`` (a file outside the repository read once into the child's environment only)
    is a declined route: no config may name it (:func:`build_client`), it exists for the unit
    test pinning that a token is never recorded, and it is untested against the real binary.
    ``call_wallclock_seconds`` bounds each subprocess; an overrun is killed and recorded with
    exit code :data:`EXIT_CODE_TIMED_OUT`.
    """

    kind = "headless_cli"

    def __init__(
        self,
        executable: str = DEFAULT_EXECUTABLE,
        call_wallclock_seconds: float = DEFAULT_CALL_WALLCLOCK_SECONDS,
        token_file: Path | None = None,
        repository_root: Path | None = None,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        resolved = shutil.which(executable) if not Path(executable).is_absolute() else executable
        if resolved is None or not Path(resolved).is_file():
            raise ModelClientError(f"headless executable {executable!r} not found on PATH")
        self.executable = str(resolved)
        if not isinstance(call_wallclock_seconds, int | float) or call_wallclock_seconds <= 0:
            raise ModelClientError("call_wallclock_seconds must be a positive number")
        self.call_wallclock_seconds = float(call_wallclock_seconds)
        self.repository_root = (repository_root or Path.cwd()).resolve()
        token: str | None = None
        if token_file is not None:
            path = Path(token_file).expanduser().resolve()
            if path.is_relative_to(self.repository_root):
                raise ModelClientError(f"token_file {path} lies inside the repository")
            if not path.is_file():
                raise ModelClientError(f"token_file {path} does not exist")
            token = path.read_text(encoding="utf-8").strip()
            if not token:
                raise ModelClientError(f"token_file {path} is empty")
        parent = dict(environment if environment is not None else os.environ)
        self.token_source = token_source_of(parent, token is not None)
        self._env, self.stripped_env_keys = child_environment(parent, token)
        assert TOKEN_ALIAS_ENV_KEY not in self._env
        self._clock = clock
        self.calls_made = 0

    def _make_cwd(self) -> str:
        cwd = tempfile.mkdtemp(prefix="arc_model_call_")
        if Path(cwd).resolve().is_relative_to(self.repository_root):
            shutil.rmtree(cwd, ignore_errors=True)
            raise ModelClientError(f"temporary cwd {cwd} lies inside the repository")
        return cwd

    @property
    def credential_present(self) -> bool:
        """Whether the child environment carries a non-empty credential variable."""
        return bool(self._env.get(TOKEN_ENV_KEY))

    def call(self, request: ModelRequest) -> ModelResponse:
        if not request.model_identifier:
            raise ModelClientError("headless_cli needs a model identifier")
        argv = headless_argv(self.executable, request.model_identifier, request.effort)
        if not self.credential_present:
            # The human's rule: absent at call time -> refuse, never attempt a login. Nothing
            # is spawned, so no process can prompt, retry or consume the allowance.
            raise CallRefused(
                REFUSAL_AUTHENTICATION_UNAVAILABLE,
                f"call {request.call_index} not attempted: {TOKEN_ENV_KEY} is absent from "
                "the environment of the calling process and no alias carries it",
                {
                    "channel": self.kind,
                    "argv": argv,
                    "cwd": None,
                    "exit_code": EXIT_CODE_NOT_STARTED,
                    "is_error": True,
                    "wallclock_seconds": 0.0,
                    "stripped_env_keys": self.stripped_env_keys,
                    "token_source": self.token_source,
                    "stderr_tail": "",
                    "response": None,
                    "usage": {},
                    "total_cost_usd": None,
                },
            )
        timeout = self.call_wallclock_seconds
        if request.wallclock_seconds_max is not None:
            timeout = min(timeout, float(request.wallclock_seconds_max))
        cwd = self._make_cwd()
        started = self._clock()
        exit_code: int
        stdout = ""
        stderr = ""
        timed_out = False
        try:
            try:
                completed = subprocess.run(
                    argv,
                    input=request.prompt,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    env=self._env,
                    timeout=timeout,
                    check=False,
                )
                exit_code = int(completed.returncode)
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = EXIT_CODE_TIMED_OUT
                stdout = _as_text(exc.stdout)
                stderr = _as_text(exc.stderr)
            except OSError as exc:
                exit_code = EXIT_CODE_NOT_STARTED
                stderr = f"{type(exc).__name__}: {exc}"
        finally:
            shutil.rmtree(cwd, ignore_errors=True)
        wallclock = self._clock() - started
        self.calls_made += 1
        parsed: dict[str, Any] | None = None
        parse_error: str | None = None
        if stdout.strip():
            try:
                loaded = json.loads(stdout)
                if isinstance(loaded, dict):
                    parsed = loaded
                else:
                    parse_error = f"stdout JSON is a {type(loaded).__name__}, not an object"
            except json.JSONDecodeError as exc:
                parse_error = f"stdout is not JSON: {exc}"
        result = parsed.get("result") if parsed is not None else None
        text = result if isinstance(result, str) else ""
        usage_raw = parsed.get("usage") if parsed is not None else None
        usage: dict[str, Any] = dict(usage_raw) if isinstance(usage_raw, dict) else {}
        is_error = bool(parsed.get("is_error")) if parsed is not None else exit_code != 0
        raw: dict[str, Any] = {
            "channel": self.kind,
            "argv": argv,
            "cwd": cwd,
            "prompt_bytes": len(request.prompt.encode("utf-8")),
            "call_wallclock_seconds": timeout,
            "timed_out": timed_out,
            "exit_code": exit_code,
            "is_error": is_error,
            "wallclock_seconds": wallclock,
            "stripped_env_keys": self.stripped_env_keys,
            "token_source": self.token_source,
            "stderr_tail": _tail(stderr, STDERR_TAIL_CHARS),
            "parse_error": parse_error,
            "stdout_tail": None if parsed is not None else _tail(stdout, STDOUT_TAIL_CHARS),
            "response": parsed,
            "result": text,
            "model": _model_reported(parsed),
            "usage": usage,
            "total_cost_usd": parsed.get("total_cost_usd") if parsed is not None else None,
        }
        if exit_code != 0 or is_error or not text:
            refusal = classify_refusal(exit_code, [stderr, text, "" if parsed else stdout])
            if refusal is not None:
                message = _tail(stderr.strip() or text.strip() or stdout.strip(), 500)
                raise CallRefused(
                    refusal, f"call {request.call_index} exit {exit_code}: {message}", raw
                )
        return ModelResponse(
            text=text,
            model_reported=raw["model"],
            usage=usage,
            raw=raw,
            exit_code=exit_code,
            wallclock_seconds=wallclock,
            cwd=cwd,
            tools_disabled=True,
            extra={"is_error": is_error, "timed_out": timed_out},
        )

    def close(self) -> None:
        return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _model_reported(parsed: Mapping[str, Any] | None) -> str | None:
    """The model the CLI reports: the key of ``modelUsage`` when there is exactly one, else
    the ``model`` field if present."""
    if parsed is None:
        return None
    usage = parsed.get("modelUsage")
    if isinstance(usage, Mapping) and len(usage) == 1:
        return str(next(iter(usage)))
    model = parsed.get("model")
    return str(model) if isinstance(model, str) else None


def build_client(spec: Mapping[str, Any] | None, root: Path) -> ModelClient | None:
    """A client from ``runner_params.model_client``. ``None`` means no model at all.

    ``kind`` ``recorded`` needs ``responses_file`` (relative to ``root``). ``headless_cli``
    accepts ``executable`` (default ``claude``) and ``call_wallclock_seconds`` (default 600);
    ``token_file`` is refused (the declined route: the credential is forwarded from the
    calling process's environment and is never written to disk); ``root`` is the repository
    the call's cwd must lie outside of.
    """
    if spec is None:
        return None
    if not isinstance(spec, Mapping) or not isinstance(spec.get("kind"), str):
        raise ModelClientError("model_client must be a mapping with a string kind")
    kind = str(spec["kind"])
    if kind not in CLIENT_KINDS:
        raise ModelClientError(f"model_client.kind {kind!r} not in {CLIENT_KINDS}")
    if kind == "none":
        return None
    if kind == "recorded":
        raw = spec.get("responses_file")
        if not isinstance(raw, str) or not raw:
            raise ModelClientError("model_client.responses_file is required for kind recorded")
        path = Path(raw)
        return RecordedResponseClient(path if path.is_absolute() else root / path)
    if "token_file" in spec:
        raise ModelClientError(
            "model_client.token_file is a declined credential route (the human's answer of "
            "2026-09-04): the token is forwarded from the environment and never read from disk"
        )
    allowed = {"kind", "executable", "call_wallclock_seconds"}
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ModelClientError(f"model_client keys {unknown} are not understood for headless_cli")
    executable = spec.get("executable", DEFAULT_EXECUTABLE)
    if not isinstance(executable, str) or not executable:
        raise ModelClientError("model_client.executable must be a non-empty string")
    seconds = spec.get("call_wallclock_seconds", DEFAULT_CALL_WALLCLOCK_SECONDS)
    if isinstance(seconds, bool) or not isinstance(seconds, int | float) or seconds <= 0:
        raise ModelClientError("model_client.call_wallclock_seconds must be a positive number")
    return HeadlessCliClient(
        executable=executable,
        call_wallclock_seconds=float(seconds),
        repository_root=root,
    )


def model_client_sha256() -> str:
    """SHA-256 of this file, recorded in every E300 results.json as model_client_sha256."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


__all__ = [
    "AUTH_SIGNATURES",
    "CLIENT_KINDS",
    "DEFAULT_CALL_WALLCLOCK_SECONDS",
    "DEFAULT_EXECUTABLE",
    "EXIT_CODE_NOT_STARTED",
    "EXIT_CODE_TIMED_OUT",
    "PURPOSES",
    "REFUSAL_AUTH",
    "REFUSAL_AUTHENTICATION_UNAVAILABLE",
    "REFUSAL_USAGE_LIMIT",
    "STRIPPED_ENV_KEYS",
    "STRIPPED_ENV_PREFIXES",
    "TOKEN_ALIAS_ENV_KEY",
    "TOKEN_ENV_KEY",
    "TOKEN_SOURCES",
    "USAGE_KEYS",
    "USAGE_LIMIT_SIGNATURES",
    "CallRefused",
    "HeadlessCliClient",
    "ModelClient",
    "ModelClientError",
    "ModelRequest",
    "ModelResponse",
    "RecordedResponseClient",
    "ResponsesExhausted",
    "build_client",
    "canonical_response_text",
    "child_environment",
    "classify_refusal",
    "extract_program_source",
    "headless_argv",
    "model_client_sha256",
]
