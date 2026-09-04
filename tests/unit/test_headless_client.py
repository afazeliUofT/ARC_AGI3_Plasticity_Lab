"""The headless CLI adapter (G3.5) against a fake ``claude`` executable, and the compact
history encoding. No real model, no network: the fake records its argv, cwd, stdin and
environment and prints whatever JSON the test asked for."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from arc_plasticity.agents import history_encoding as he
from arc_plasticity.agents import model_client as mc
from arc_plasticity.environments import arc_interface as ai
from arc_plasticity.hypotheses.interface import (
    Observation,
    history_from_wire,
    history_to_wire,
    observation_to_wire,
)
from tests.g3_synthetic import DEFAULT_ACTIONS, synthetic_history

ROOT = Path(__file__).resolve().parents[2]
ENV_DIR = ROOT / "environment_files"


def _fake_claude(tmp_path: Path, stdout: str, exit_code: int = 0, sleep: float = 0) -> Path:
    """A shell script standing in for ``claude``: records what it received, prints ``stdout``."""
    record = tmp_path / "record.json"
    recorder = tmp_path / "recorder.py"
    recorder.write_text(
        "import json, os, sys\n"
        'sys.stdin.reconfigure(encoding="utf-8")\n'
        'json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read(),\n'
        f'           "env": dict(os.environ)}}, open({str(record)!r}, "w"))\n'
    )
    script = tmp_path / "claude"
    body = f"""#!/bin/sh
python3 {recorder} "$@"
{"sleep " + str(sleep) if sleep else ""}
cat <<'OUT'
{stdout}
OUT
exit {exit_code}
"""
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _request(index: int = 1, prompt: str = "hello") -> mc.ModelRequest:
    return mc.ModelRequest(
        call_index=index,
        purpose="induce",
        prompt=prompt,
        model_identifier="claude-fable-5-1",
        effort="high",
    )


def _success_json(text: str = "```python\ndef predict(h, a):\n    return h[-1]\n```") -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": text,
            "session_id": "abc",
            "total_cost_usd": None,
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 300,
                "cache_creation_input_tokens": 40,
                "cache_read_input_tokens": 7,
            },
            "modelUsage": {"claude-fable-5-1-20260601": {"inputTokens": 1200}},
        }
    )


def test_headless_call_flags_cwd_stdin_env_and_usage(tmp_path: Path) -> None:
    script = _fake_claude(tmp_path, _success_json())
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "ARC_API_KEY": "secret-benchmark-key",
        "ARC_OTHER": "x",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_ENTRYPOINT": "sdk-cli",
        "KEEP_ME": "yes",
    }
    client = mc.HeadlessCliClient(
        executable=str(script),
        call_wallclock_seconds=30,
        repository_root=ROOT,
        environment=env,
    )
    assert client.kind == "headless_cli" and client.token_source == "none"
    assert client.stripped_env_keys == [
        "ARC_API_KEY",
        "ARC_OTHER",
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
    ]
    response = client.call(_request(prompt="the prompt\nwith two lines"))
    record = json.loads((tmp_path / "record.json").read_text())
    assert record["argv"] == [
        "-p",
        "--output-format",
        "json",
        "--model",
        "claude-fable-5-1",
        "--effort",
        "high",
        "--tools",
        "",
        "--permission-prompts",
        "none",
        "--no-session-persistence",
    ]
    assert "--continue" not in record["argv"] and "--resume" not in record["argv"]
    assert record["stdin"] == "the prompt\nwith two lines"
    assert "ARC_API_KEY" not in record["env"] and "CLAUDECODE" not in record["env"]
    assert record["env"]["KEEP_ME"] == "yes" and "CLAUDE_CODE_OAUTH_TOKEN" not in record["env"]
    cwd = Path(record["cwd"])
    assert cwd == Path(response.cwd).resolve() or cwd == Path(response.cwd)
    assert not cwd.is_relative_to(ROOT) and not cwd.exists()
    assert response.exit_code == 0 and response.tools_disabled and not response.extra["is_error"]
    assert response.text.startswith("```python") and response.model_reported == (
        "claude-fable-5-1-20260601"
    )
    assert response.tokens_by_kind() == {
        "input": 1200,
        "output": 300,
        "cache_creation": 40,
        "cache_read": 7,
    }
    assert response.raw["argv"][0] == str(script) and response.raw["total_cost_usd"] is None
    assert response.raw["response"]["session_id"] == "abc" and response.raw["parse_error"] is None
    assert response.raw["token_source"] == "none" and response.wallclock_seconds >= 0
    assert "secret-benchmark-key" not in mc.canonical_response_text(response.raw)
    assert client.calls_made == 1
    client.close()


def test_headless_token_file_is_exported_and_never_recorded(tmp_path: Path) -> None:
    script = _fake_claude(tmp_path, _success_json("ok"))
    token_file = tmp_path / "token.txt"
    token_file.write_text("sk-ant-oat01-SECRET\n")
    client = mc.HeadlessCliClient(
        executable=str(script),
        token_file=token_file,
        repository_root=ROOT,
        environment={"PATH": os.environ["PATH"]},
    )
    assert client.token_source == "file"
    response = client.call(_request())
    record = json.loads((tmp_path / "record.json").read_text())
    assert record["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-SECRET"
    assert "SECRET" not in mc.canonical_response_text(response.raw)
    assert "SECRET" not in json.dumps(dict(response.extra))
    inside = ROOT / "token_inside_repo.txt"
    with pytest.raises(mc.ModelClientError, match="inside the repository"):
        mc.HeadlessCliClient(executable=str(script), token_file=inside, repository_root=ROOT)
    with pytest.raises(mc.ModelClientError, match="does not exist"):
        mc.HeadlessCliClient(
            executable=str(script), token_file=tmp_path / "missing", repository_root=ROOT
        )
    empty = tmp_path / "empty.txt"
    empty.write_text(" \n")
    with pytest.raises(mc.ModelClientError, match="is empty"):
        mc.HeadlessCliClient(executable=str(script), token_file=empty, repository_root=ROOT)
    env_client = mc.HeadlessCliClient(
        executable=str(script),
        repository_root=ROOT,
        environment={"PATH": os.environ["PATH"], "CLAUDE_CODE_OAUTH_TOKEN": "from-env"},
    )
    assert env_client.token_source == "environment"


def test_headless_nonzero_exit_is_a_made_call_without_program(tmp_path: Path) -> None:
    script = _fake_claude(tmp_path, "boom, not json", exit_code=3)
    client = mc.HeadlessCliClient(
        executable=str(script), repository_root=ROOT, environment={"PATH": os.environ["PATH"]}
    )
    response = client.call(_request())
    assert response.exit_code == 3 and response.text == "" and response.extra["is_error"]
    assert response.tokens_total() == 0 and response.model_reported is None
    assert response.raw["parse_error"].startswith("stdout is not JSON")
    assert response.raw["stdout_tail"] == "boom, not json\n"
    assert mc.extract_program_source(response.text) == "\n"


def test_headless_is_error_result_is_a_made_call(tmp_path: Path) -> None:
    payload = json.dumps(
        {"type": "result", "subtype": "error_during_execution", "is_error": True,
         "result": "API Error: 529 overloaded", "usage": {"input_tokens": 5}}
    )  # fmt: skip
    script = _fake_claude(tmp_path, payload, exit_code=0)
    client = mc.HeadlessCliClient(
        executable=str(script), repository_root=ROOT, environment={"PATH": os.environ["PATH"]}
    )
    response = client.call(_request())
    assert (
        response.exit_code == 0
        and response.extra["is_error"]
        and response.text.startswith("API Error")
    )
    assert response.tokens_by_kind()["input"] == 5


@pytest.mark.parametrize(
    ("stdout", "exit_code", "reason"),
    [
        ("Not logged in. Please run /login", 1, "auth"),
        (json.dumps({"is_error": True, "result": "Login expired · Please run /login"}), 0, "auth"),
        (
            json.dumps(
                {"is_error": True, "result": "You've hit your session limit - resets 3:30pm"}
            ),
            0,
            "usage_limit",
        ),
        (
            "You've hit your org's monthly spend limit - ask your admin to raise it",
            1,
            "usage_limit",
        ),
    ],
)
def test_headless_refuses_on_auth_and_usage_limit_signatures(
    tmp_path: Path, stdout: str, exit_code: int, reason: str
) -> None:
    script = _fake_claude(tmp_path, stdout, exit_code=exit_code)
    client = mc.HeadlessCliClient(
        executable=str(script), repository_root=ROOT, environment={"PATH": os.environ["PATH"]}
    )
    with pytest.raises(mc.CallRefused) as info:
        client.call(_request())
    assert info.value.reason == reason and isinstance(info.value, mc.ModelClientError)
    assert info.value.raw["exit_code"] == exit_code
    # A successful answer that merely mentions a limit is not a refusal.
    ok = _fake_claude(tmp_path, _success_json("no usage limit here, program follows"))
    client = mc.HeadlessCliClient(
        executable=str(ok), repository_root=ROOT, environment={"PATH": os.environ["PATH"]}
    )
    assert client.call(_request()).text.startswith("no usage limit")


def test_headless_timeout_is_recorded(tmp_path: Path) -> None:
    script = _fake_claude(tmp_path, _success_json(), sleep=5)
    client = mc.HeadlessCliClient(
        executable=str(script),
        call_wallclock_seconds=0.5,
        repository_root=ROOT,
        environment={"PATH": os.environ["PATH"]},
    )
    response = client.call(_request())
    assert response.exit_code == mc.EXIT_CODE_TIMED_OUT and response.extra["timed_out"]
    assert response.text == "" and response.raw["timed_out"] and response.wallclock_seconds < 5


def test_headless_constructor_validation(tmp_path: Path) -> None:
    with pytest.raises(mc.ModelClientError, match="not found on PATH"):
        mc.HeadlessCliClient(executable="no-such-claude-binary-xyz", repository_root=ROOT)
    with pytest.raises(mc.ModelClientError, match="not found"):
        mc.HeadlessCliClient(executable=str(tmp_path / "absent"), repository_root=ROOT)
    script = _fake_claude(tmp_path, _success_json())
    with pytest.raises(mc.ModelClientError, match="positive"):
        mc.HeadlessCliClient(executable=str(script), call_wallclock_seconds=0, repository_root=ROOT)
    client = mc.HeadlessCliClient(executable=str(script), repository_root=ROOT)
    with pytest.raises(mc.ModelClientError, match="model identifier"):
        client.call(
            mc.ModelRequest(
                call_index=1, purpose="induce", prompt="p", model_identifier="", effort="high"
            )
        )


def test_build_client_headless_spec(tmp_path: Path) -> None:
    script = _fake_claude(tmp_path, _success_json())
    client = mc.build_client(
        {"kind": "headless_cli", "executable": str(script), "call_wallclock_seconds": 12}, ROOT
    )
    assert isinstance(client, mc.HeadlessCliClient)
    assert client.call_wallclock_seconds == 12.0 and client.repository_root == ROOT.resolve()
    with pytest.raises(mc.ModelClientError, match="not understood"):
        mc.build_client({"kind": "headless_cli", "responses_file": "x"}, ROOT)
    with pytest.raises(mc.ModelClientError, match="positive number"):
        mc.build_client({"kind": "headless_cli", "call_wallclock_seconds": -1}, ROOT)
    with pytest.raises(mc.ModelClientError, match="token_file"):
        mc.build_client({"kind": "headless_cli", "token_file": ""}, ROOT)
    with pytest.raises(mc.ModelClientError, match="not found on PATH"):
        mc.build_client({"kind": "headless_cli", "executable": "no-such-claude-xyz"}, ROOT)


def test_classify_refusal_and_child_environment() -> None:
    assert mc.classify_refusal(1, ["", "Invalid API key"]) == "auth"
    assert mc.classify_refusal(1, ["rate_limit_error"]) == "usage_limit"
    assert mc.classify_refusal(1, ["segmentation fault"]) is None
    assert mc.classify_refusal(1, ["", None]) is None  # type: ignore[list-item]
    env, stripped = mc.child_environment({"ARC_API_KEY": "k", "X": "1"}, "tok")
    assert env == {"X": "1", "CLAUDE_CODE_OAUTH_TOKEN": "tok"} and stripped == ["ARC_API_KEY"]


# --------------------------------------------------------------------------- encoding


def _summary_wire(summary: ai.FrameSummary) -> dict[str, Any]:
    return observation_to_wire(
        Observation(
            frame=summary.frames,
            state=summary.state,
            levels_completed=summary.levels_completed,
            available_actions=summary.available_actions,
        )
    )


def test_encoding_round_trips_synthetic_and_edge_cases() -> None:
    records = history_to_wire(synthetic_history(DEFAULT_ACTIONS))
    assert len(records) > 3
    text = he.encode_history_compact(records)
    assert he.decode_history_compact(text) == records
    assert text.startswith("record 0: reset; state=")
    # Two grids of different shapes, a state with a quote, a click action, a negative cell.
    odd = [
        {
            "action": None,
            "frame": [[[1, 1, 2], [1, 1, 2]], [[0]]],
            "state": 'A"B; levels_completed=9',
            "levels_completed": 0,
            "available_actions": [6],
        },
        {
            "action": {"action": 6, "data": {"x": 3, "y": 4}},
            "frame": [[[1, 1, 2], [1, -1, 2]], [[0]]],
            "state": "WIN",
            "levels_completed": 1,
            "available_actions": [],
        },
        {
            "action": {"action": 1, "data": {}},
            "frame": [[[5, 5]]],
            "state": "GAME_OVER",
            "levels_completed": 1,
            "available_actions": [1, 2],
        },
        {
            "action": {"action": 2, "data": {}},
            "frame": [[[5, 5]]],
            "state": "GAME_OVER",
            "levels_completed": 1,
            "available_actions": [1, 2],
        },
    ]
    text = he.encode_history_compact(odd)
    assert "frame: delta from record 0, 1 cell(s)\ng0 (1,1)=-1" in text
    assert "frame: full, 1 grid(s)\ng0 r0: 5*2" in text  # shape changed: full
    assert "frame: unchanged from record 2" in text
    assert he.decode_history_compact(text) == odd
    with pytest.raises(he.HistoryEncodingError):
        he.decode_history_compact(
            'record 1: reset; state="x"; levels_completed=0; available_actions=[]\n'
        )
    with pytest.raises(he.HistoryEncodingError):
        he.decode_history_compact(text.replace("1 cell(s)", "2 cell(s)"))


@pytest.mark.skipif(not (ENV_DIR / "ls20").exists(), reason="environment cache absent")
def test_encoding_is_lossless_and_compact_on_ls20() -> None:
    manifest = json.loads((ROOT / "experiments" / "environment_cache_manifest.json").read_text())
    game_id = next(str(g["game_id"]) for g in manifest["games"] if g.get("stem") == "ls20")
    arcade = ai.open_offline_arcade(ENV_DIR)
    env = ai.make_environment(arcade, game_id, 12345)
    reset = env.reset()
    assert reset is not None
    history: list[dict[str, Any]] = [
        {"action": None, **_summary_wire(ai.summarize_response(reset))}
    ]
    for a in (1, 2, 3, 4):
        action = ai.ActionRecord(action=a, data={})
        frame = ai.step_environment(env, action)
        assert frame is not None
        history.append({"action": {"action": a, "data": {}}, **_summary_wire(frame)})
    raw = json.dumps(history, separators=(",", ":"))
    text = he.encode_history_compact(history)
    assert he.decode_history_compact(text) == history
    assert history_to_wire(history_from_wire(history)) == history
    assert len(text) < len(raw) / 4, (len(text), len(raw))


def test_history_encoding_sha256_is_the_file_digest() -> None:
    expected = hashlib.sha256(Path(he.__file__).read_bytes()).hexdigest()
    assert he.history_encoding_sha256() == expected
