"""The model-call channel (G3.4): the recorded-response stub, the client builder and the
program extractor. No model, no network, no process."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from arc_plasticity.agents import model_client as mc

ROOT = Path(__file__).resolve().parents[2]


def _responses(tmp_path: Path, items: list[dict[str, object]]) -> Path:
    path = tmp_path / "responses.json"
    path.write_text(json.dumps({"schema_version": 1, "responses": items}))
    return path


def _request(index: int = 1, purpose: str = "induce") -> mc.ModelRequest:
    return mc.ModelRequest(
        call_index=index,
        purpose=purpose,
        prompt=f"prompt {index}",
        model_identifier="claude-fable-5-1",
        effort="high",
    )


def test_recorded_client_replays_in_order_then_refuses(tmp_path: Path) -> None:
    path = _responses(
        tmp_path,
        [
            {
                "text": "```python\ndef predict(h, a):\n    return h[-1]\n```",
                "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 2},
                "model": "stub-model",
            },
            {"text": "second", "usage": {}},
        ],
    )
    client = mc.RecordedResponseClient(path)
    assert client.kind == "recorded" and client.remaining == 2
    first = client.call(_request(1))
    assert first.text.startswith("```python") and first.model_reported == "stub-model"
    assert first.tokens_by_kind() == {
        "input": 10,
        "output": 5,
        "cache_creation": 0,
        "cache_read": 2,
    }
    assert first.tokens_total() == 17 and first.exit_code == 0 and first.tools_disabled
    assert not ROOT.is_relative_to(first.cwd) and not Path(first.cwd).is_relative_to(ROOT)
    assert not Path(first.cwd).exists()  # the stub's cwd is removed after the call
    assert first.raw["responses_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        first.response_sha256
        == hashlib.sha256(mc.canonical_response_text(first.raw).encode()).hexdigest()
    )
    second = client.call(_request(2, "revise"))
    assert second.text == "second" and second.tokens_total() == 0 and client.remaining == 0
    with pytest.raises(mc.ResponsesExhausted, match="exhausted after 2"):
        client.call(_request(3))
    assert client.calls_made == 2
    client.close()


def test_recorded_client_validates_its_file(tmp_path: Path) -> None:
    with pytest.raises(mc.ModelClientError, match="does not exist"):
        mc.RecordedResponseClient(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"responses": [{"usage": {}}]}))
    with pytest.raises(mc.ModelClientError, match="lacks a text string"):
        mc.RecordedResponseClient(bad)
    bad.write_text(json.dumps([]))
    with pytest.raises(mc.ModelClientError, match="lacks a responses list"):
        mc.RecordedResponseClient(bad)


def test_request_validation() -> None:
    with pytest.raises(ValueError, match="purpose"):
        _request(1, "guess")
    with pytest.raises(ValueError, match="1-based"):
        _request(0)
    assert _request(1).prompt_sha256 == hashlib.sha256(b"prompt 1").hexdigest()


def test_extract_program_source_prefers_the_first_python_fence() -> None:
    text = "Here you go:\n```python\ndef predict(h, a):\n    return h[-1]\n```\nand ```py\nx=1\n```"
    assert mc.extract_program_source(text) == "def predict(h, a):\n    return h[-1]\n"
    assert mc.extract_program_source("```\nplain\n```") == "plain\n"
    assert mc.extract_program_source("def predict(h, a): return h[-1]  \n\n") == (
        "def predict(h, a): return h[-1]\n"
    )


def test_build_client_kinds(tmp_path: Path) -> None:
    assert mc.build_client(None, ROOT) is None
    assert mc.build_client({"kind": "none"}, ROOT) is None
    path = _responses(tmp_path, [{"text": "x"}])
    client = mc.build_client({"kind": "recorded", "responses_file": str(path)}, ROOT)
    assert isinstance(client, mc.RecordedResponseClient)
    relative = mc.build_client({"kind": "recorded", "responses_file": "responses.json"}, tmp_path)
    assert isinstance(relative, mc.RecordedResponseClient)
    if shutil.which("claude") is not None:  # G3.5: the adapter exists; a real CLI on PATH
        headless = mc.build_client({"kind": "headless_cli"}, ROOT)
        assert isinstance(headless, mc.HeadlessCliClient) and headless.kind == "headless_cli"
        assert headless.call_wallclock_seconds == mc.DEFAULT_CALL_WALLCLOCK_SECONDS
    with pytest.raises(mc.ModelClientError, match="not found on PATH"):
        mc.build_client({"kind": "headless_cli", "executable": "no-such-claude-xyz"}, ROOT)
    with pytest.raises(mc.ModelClientError, match="not in"):
        mc.build_client({"kind": "api"}, ROOT)
    with pytest.raises(mc.ModelClientError, match="responses_file"):
        mc.build_client({"kind": "recorded"}, ROOT)
    with pytest.raises(mc.ModelClientError, match="string kind"):
        mc.build_client({"responses_file": "x"}, ROOT)


def test_model_client_sha256_is_the_file_digest() -> None:
    expected = hashlib.sha256(Path(mc.__file__).read_bytes()).hexdigest()
    assert mc.model_client_sha256() == expected
