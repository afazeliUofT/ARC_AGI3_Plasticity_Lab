"""The language-model channel of the reference architecture (preregistration/G3.yaml
``model_calls``).

Two clients share one interface, :class:`ModelClient`:

* :class:`RecordedResponseClient` replays canned responses from a JSON file in order and
  refuses (:class:`ResponsesExhausted`) once they are used up. Holding the responses fixed
  makes the E300 runner a deterministic function of the experiment seed, which is what
  ``model_calls.nondeterminism_protocol`` asks ``tests/unit`` to assert. It makes no
  process, no network call and reads nothing but its file.
* The headless CLI adapter (``kind`` ``headless_cli``: one ``claude -p`` per call, fresh
  session, tool use disabled, cwd a fresh temporary directory outside the repository) is
  G3.5 and is refused here until it exists, so no run can start believing it has a model.

Every call is described by a :class:`ModelRequest` and answered by a :class:`ModelResponse`
whose fields are exactly what ``model_calls.jsonl`` records: model as sent and as reported,
effort, cwd, ``tools_disabled``, the verbatim usage mapping, wall-clock and exit code. The
digest of this file (:func:`model_client_sha256`) goes into every E300 ``results.json``.
This module defines no threshold.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
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


class ModelClientError(RuntimeError):
    """A call could not be made at all (no client, no credential, no response left)."""


class ResponsesExhausted(ModelClientError):
    """The recorded response file has no response left for this call."""


@dataclass(frozen=True)
class ModelRequest:
    call_index: int
    purpose: str
    prompt: str
    model_identifier: str
    effort: str

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise ValueError(f"purpose {self.purpose!r} not in {PURPOSES}")
        if self.call_index < 1:
            raise ValueError("call_index is 1-based")

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


def build_client(spec: Mapping[str, Any] | None, root: Path) -> ModelClient | None:
    """A client from ``runner_params.model_client``. ``None`` means no model at all.

    ``kind`` ``recorded`` needs ``responses_file`` (relative to ``root``); ``headless_cli``
    is refused until G3.5 lands it, so a run cannot start believing it has a model.
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
    raise ModelClientError(
        "model_client.kind headless_cli is not implemented yet (G3.5); no model call can be made"
    )


def model_client_sha256() -> str:
    """SHA-256 of this file, recorded in every E300 results.json as model_client_sha256."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


__all__ = [
    "CLIENT_KINDS",
    "PURPOSES",
    "USAGE_KEYS",
    "ModelClient",
    "ModelClientError",
    "ModelRequest",
    "ModelResponse",
    "RecordedResponseClient",
    "ResponsesExhausted",
    "build_client",
    "canonical_response_text",
    "extract_program_source",
    "model_client_sha256",
]
