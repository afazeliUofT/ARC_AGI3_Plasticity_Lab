"""The RHAE adapter against the eight hand-computed vectors hash-locked in the G2 pre-registration.

Every expected number, tolerance, case-count bound and required tag is read from the real
``preregistration/G2.yaml`` through the verifier's own ``load_preregistration`` so this file
carries no copy of a gate threshold. Because the adapter delegates to
``arc_agi.scorecard.EnvironmentScoreCalculator``, a failure here is either an adapter bug or a
substrate finding about the toolkit; the pre-registration forbids editing a case in response.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from arc_plasticity.evaluation import rhae

ROOT = Path(__file__).resolve().parents[2]
RHAE_SOURCE = ROOT / "src" / "arc_plasticity" / "evaluation" / "rhae.py"

# Cases whose alternative_form_values all differ from the pre-registered expectation. C4 is
# excluded on purpose: its min_1_15_then_square alternative coincides with the expected value
# (the pre-registration records this in its arithmetic), so C4 discriminates only the other
# three forms and is covered by the expected-value assertion alone.
DISCRIMINATING_CASES = (
    "C3_cap_discriminator",
    "C5_three_way_discriminator",
    "C6_level_weighting",
    "C7_completion_cap_binding",
    "C8_plain_mean_over_environments",
)


def _load_verify_run() -> ModuleType:
    if "verify_run" in sys.modules:
        return sys.modules["verify_run"]
    spec = importlib.util.spec_from_file_location("verify_run", ROOT / "scripts" / "verify_run.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def prereg() -> dict[str, Any]:
    data, _, _ = _load_verify_run().load_preregistration("G2", ROOT)
    return data


@pytest.fixture(scope="module")
def cases(prereg: dict[str, Any]) -> list[dict[str, Any]]:
    vectors = prereg["rhae"]["synthetic_vectors"]
    assert isinstance(vectors, list) and vectors
    return vectors


@pytest.fixture(scope="module")
def tolerance(prereg: dict[str, Any]) -> float:
    return float(prereg["thresholds"]["rhae_synthetic_abs_tolerance"])


def test_case_count_within_preregistered_bounds(
    prereg: dict[str, Any], cases: list[dict[str, Any]]
) -> None:
    lo = prereg["thresholds"]["rhae_synthetic_cases_min"]
    hi = prereg["thresholds"]["rhae_synthetic_cases_max"]
    assert lo <= len(cases) <= hi, (len(cases), lo, hi)
    ids = [c["id"] for c in cases]
    assert len(set(ids)) == len(ids), f"duplicate case ids: {ids}"


def test_every_required_tag_is_covered(prereg: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    required = set(prereg["thresholds"]["rhae_synthetic_required_tags"])
    present = {tag for case in cases for tag in case["tags"]}
    assert required <= present, f"missing tags: {sorted(required - present)}"


def test_all_cases_match_expected_values(cases: list[dict[str, Any]], tolerance: float) -> None:
    failures: list[str] = []
    for case in cases:
        env_scores, total = rhae.score_vector_case(case)
        expected_envs = [float(x) for x in case["expected_environment_scores"]]
        expected_total = float(case["expected_total"])
        if len(env_scores) != len(expected_envs):
            failures.append(f"{case['id']}: {len(env_scores)} envs, expected {len(expected_envs)}")
            continue
        for i, (got, want) in enumerate(zip(env_scores, expected_envs, strict=True)):
            if abs(got - want) > tolerance:
                failures.append(f"{case['id']} env {i}: got {got!r}, expected {want!r}")
        if abs(total - expected_total) > tolerance:
            failures.append(f"{case['id']} total: got {total!r}, expected {expected_total!r}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("case_id", DISCRIMINATING_CASES)
def test_alternative_forms_are_not_produced(
    cases: list[dict[str, Any]], tolerance: float, case_id: str
) -> None:
    case = next(c for c in cases if c["id"] == case_id)
    alternatives = case["alternative_form_values"]
    assert alternatives, f"{case_id} has no alternative_form_values"
    env_scores, total = rhae.score_vector_case(case)
    # Single-environment cases discriminate on the environment score; C8 on the total.
    produced = total if len(env_scores) > 1 else env_scores[0]
    for name, value in alternatives.items():
        assert abs(produced - float(value)) > tolerance, (
            f"{case_id}: adapter produced {produced!r}, which is the {name} form ({value!r})"
        )


def test_adapter_delegates_to_toolkit_textually() -> None:
    """Mirror of the verifier's rhae_adapter_must_delegate_to_toolkit check."""
    text = RHAE_SOURCE.read_text()
    assert "EnvironmentScoreCalculator" in text
    assert "from arc_agi" in text or "import arc_agi" in text
    assert rhae.EnvironmentScoreCalculator.__module__ == "arc_agi.scorecard"


def test_total_score_of_nothing_is_zero() -> None:
    assert rhae.total_score([]) == 0.0
    assert rhae.environment_score([]) == 0.0


def test_uncompleted_level_actions_do_not_influence_score() -> None:
    base = [rhae.LevelOutcome(10, 10, True), rhae.LevelOutcome(10, 0, False)]
    more = [rhae.LevelOutcome(10, 10, True), rhae.LevelOutcome(10, 999, False)]
    assert rhae.environment_score(base) == rhae.environment_score(more)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"human_baseline_actions": 0, "agent_actions": 1, "completed": True},
        {"human_baseline_actions": -1, "agent_actions": 1, "completed": True},
        {"human_baseline_actions": 5, "agent_actions": -1, "completed": False},
        {"human_baseline_actions": 5.0, "agent_actions": 1, "completed": True},
        {"human_baseline_actions": 5, "agent_actions": True, "completed": True},
        {"human_baseline_actions": 5, "agent_actions": 1, "completed": 1},
    ],
)
def test_invalid_level_outcomes_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(rhae.RhaeInputError):
        rhae.LevelOutcome(**kwargs)


def test_non_level_outcome_in_sequence_is_rejected() -> None:
    with pytest.raises(rhae.RhaeInputError):
        rhae.environment_score([{"human": 1, "agent": 1, "completed": True}])  # type: ignore[list-item]
