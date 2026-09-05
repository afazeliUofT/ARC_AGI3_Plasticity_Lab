"""The G3.6b diagnosis script's static classifier must tell copied, literal and computed
``levels_completed`` apart, because the decision rule reads its totals."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "g36b_plan_diagnosis.py"


@pytest.fixture(scope="module")
def diagnosis():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("g36b_plan_diagnosis", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_copied_from_last_record(diagnosis, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        "h001.py",
        "def predict(history, action):\n"
        "    last = history[-1]\n"
        "    return {'frame': last['frame'], 'state': last['state'],\n"
        "            'levels_completed': last['levels_completed'],\n"
        "            'available_actions': list(last['available_actions'])}\n",
    )
    report = diagnosis.analyse_program(path)
    assert report["kinds"] == ["copied_from_input_record"]
    assert report["never_computes_levels"] is True
    assert report["arithmetic_on_key"] == []


def test_copied_via_get_and_name(diagnosis, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        "h002.py",
        "def predict(history, action):\n"
        "    levels = history[-1].get('levels_completed', 0)\n"
        "    if action['action'] == 0:\n"
        "        return {'frame': [], 'state': 'NOT_FINISHED', 'levels_completed': levels,\n"
        "                'available_actions': []}\n"
        "    return {'frame': [], 'state': 'NOT_FINISHED', 'levels_completed': levels,\n"
        "            'available_actions': []}\n",
    )
    report = diagnosis.analyse_program(path)
    assert report["kinds"] == ["via_name:copied_from_input_record"]
    assert len(report["returned_levels_completed"]) == 2
    assert report["never_computes_levels"] is True


def test_literal_zero(diagnosis, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        "h003.py",
        "def predict(history, action):\n"
        "    return {'frame': [], 'state': 'NOT_FINISHED', 'levels_completed': 0,\n"
        "            'available_actions': []}\n",
    )
    report = diagnosis.analyse_program(path)
    assert report["kinds"] == ["literal:0"]
    assert report["never_computes_levels"] is True


def test_computed_win_condition_is_not_classified_as_useless(
    diagnosis,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        "h004.py",
        "def predict(history, action):\n"
        "    last = history[-1]\n"
        "    done = last['frame'][0][0][0] == 9\n"
        "    levels = last['levels_completed'] + (1 if done else 0)\n"
        "    return {'frame': last['frame'], 'state': 'WIN' if done else last['state'],\n"
        "            'levels_completed': levels, 'available_actions': []}\n",
    )
    report = diagnosis.analyse_program(path)
    assert report["kinds"] == ["via_name:computed:BinOp"]
    assert report["arithmetic_on_key"] == [4]
    assert report["never_computes_levels"] is False
    assert report["mentions_WIN_state"] is True
