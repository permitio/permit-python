"""Tests for the CI job and two Workflow Hardening checks in .github/workflows/test.yml.

The CI job, the job-list check and the local actions' shellcheck are bash in a
workflow `run:` block. These tests read each block and its `env:` from test.yml
with yq, and run it the way GitHub runs a `shell: bash` step, against planted
job results, planted workflows and planted actions. They need bash, jq, yq
(mikefarah v4) and shellcheck on PATH, as GitHub's ubuntu-24.04 runners have them.

Run with:
uv run --only-dev pytest -c .github/scripts/pytest.ini .github/scripts/test_ci_checks.py
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"
CI_STEP = ("ci", "Check the needed jobs")
NEEDS_CHECK_STEP = ("workflow-hardening", "Check that CI needs every job")
SHELLCHECK_STEP = ("workflow-hardening", "Shellcheck the local actions")
ADVISORY_JOB = "e2e-unpinned-pdp"


def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.fail(f"{name} is not on PATH; these tests run the workflow's bash, which needs it")
    return path


def read_workflow(path: Path) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603 - yq reads the workflow file under test
        [tool("yq"), "-o=json", ".", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    workflow: dict[str, Any] = json.loads(completed.stdout)
    return workflow


def find_step(workflow: dict[str, Any], job_and_step: tuple[str, str]) -> dict[str, Any]:
    job, name = job_and_step
    steps: list[dict[str, Any]] = [
        step for step in workflow["jobs"][job]["steps"] if step.get("name") == name
    ]
    assert len(steps) == 1, f"expected one step named {name!r} in job {job!r}, found {len(steps)}"
    return steps[0]


def run_step(
    step: dict[str, Any], tmp_path: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Runs a step's `run:` block as `shell: bash` does, with its env and `env` on top."""
    assert step["shell"] == "bash"
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    step_env = {key: str(value) for key, value in step.get("env", {}).items()}
    return subprocess.run(  # noqa: S603 - bash runs the workflow's own step script
        [tool("bash"), "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        env={"PATH": os.environ["PATH"], **step_env, **env},
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return read_workflow(WORKFLOW)


@pytest.fixture(scope="module")
def needed(workflow: dict[str, Any]) -> list[str]:
    needs: list[str] = workflow["jobs"]["ci"]["needs"]
    return needs


# --- the CI job ---------------------------------------------------------------


def results(needed: list[str], overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """`toJSON(needs)` for the given jobs, each a success unless `overrides` gives its result."""
    overrides = overrides or {}
    return {job: {"result": overrides.get(job, "success"), "outputs": {}} for job in needed}


def run_ci(
    workflow: dict[str, Any], tmp_path: Path, needs: dict[str, Any] | str, event: str
) -> subprocess.CompletedProcess[str]:
    raw = needs if isinstance(needs, str) else json.dumps(needs)
    return run_step(find_step(workflow, CI_STEP), tmp_path, {"NEEDS": raw, "EVENT": event})


def test_ci_is_named_ci_and_runs_whatever_happened_to_its_needs(workflow: dict[str, Any]) -> None:
    ci = workflow["jobs"]["ci"]
    assert ci["name"] == "CI"
    assert ci["if"] == "always()"


def test_ci_does_not_need_the_advisory_job(needed: list[str]) -> None:
    assert ADVISORY_JOB not in needed


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_ci_passes_when_every_needed_job_succeeded(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path, event: str
) -> None:
    completed = run_ci(workflow, tmp_path, results(needed), event)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "::error" not in completed.stdout


@pytest.mark.parametrize("event", ["pull_request", "push"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_ci_fails_when_a_needed_job_did_not_succeed(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path, result: str, event: str
) -> None:
    completed = run_ci(workflow, tmp_path, results(needed, {"pytest": result}), event)
    assert completed.returncode == 1
    assert f"::error title=CI::Jobs that did not succeed: pytest {result}" in completed.stdout


def test_ci_names_every_job_that_did_not_succeed(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    needs = results(needed, {"audit": "failure", "comment": "skipped"})
    completed = run_ci(workflow, tmp_path, needs, "pull_request")
    assert completed.returncode == 1
    assert "Jobs that did not succeed: audit failure, comment skipped" in completed.stdout


def test_ci_lets_dependency_review_be_skipped_on_a_push(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    completed = run_ci(
        workflow, tmp_path, results(needed, {"dependency-review": "skipped"}), "push"
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("event", ["pull_request", "workflow_dispatch", "schedule"])
def test_ci_fails_when_dependency_review_is_skipped_on_any_other_event(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path, event: str
) -> None:
    completed = run_ci(workflow, tmp_path, results(needed, {"dependency-review": "skipped"}), event)
    assert completed.returncode == 1
    assert "Jobs that did not succeed: dependency-review skipped" in completed.stdout


@pytest.mark.parametrize("result", ["failure", "cancelled"])
def test_ci_fails_when_dependency_review_does_not_succeed_on_a_push(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path, result: str
) -> None:
    completed = run_ci(workflow, tmp_path, results(needed, {"dependency-review": result}), "push")
    assert completed.returncode == 1
    assert f"Jobs that did not succeed: dependency-review {result}" in completed.stdout


def test_ci_fails_when_another_job_is_skipped_on_a_push(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    needs = results(needed, {"dependency-review": "skipped", "comment": "skipped"})
    completed = run_ci(workflow, tmp_path, needs, "push")
    assert completed.returncode == 1
    assert "Jobs that did not succeed: comment skipped" in completed.stdout


def test_ci_exits_2_when_a_job_result_is_missing(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    completed = run_ci(workflow, tmp_path, results(needed[1:]), "pull_request")
    assert completed.returncode == 2
    assert f"{len(needed) - 1} job results, expected {len(needed)}" in completed.stdout


def test_ci_exits_2_on_an_extra_job_result(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    completed = run_ci(workflow, tmp_path, results([*needed, "extra"]), "pull_request")
    assert completed.returncode == 2
    assert f"{len(needed) + 1} job results, expected {len(needed)}" in completed.stdout


@pytest.mark.parametrize("raw", ["not json", "[1]"])
def test_ci_exits_2_when_the_results_cannot_be_read(
    workflow: dict[str, Any], tmp_path: Path, raw: str
) -> None:
    completed = run_ci(workflow, tmp_path, raw, "pull_request")
    assert completed.returncode == 2
    assert "Could not read the job results" in completed.stdout


@pytest.mark.parametrize("raw", ["", "{}", "[]"])
def test_ci_exits_2_when_no_job_result_arrives(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path, raw: str
) -> None:
    completed = run_ci(workflow, tmp_path, raw, "pull_request")
    assert completed.returncode == 2
    assert f"0 job results, expected {len(needed)}" in completed.stdout


# --- the job-list check in Workflow Hardening ---------------------------------


def set_expected_jobs(planted: dict[str, Any], value: object) -> None:
    find_step(planted, CI_STEP)["env"]["EXPECTED_JOBS"] = value


def run_needs_check(
    workflow: dict[str, Any],
    tmp_path: Path,
    planted: dict[str, Any] | None,
    advisory: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Runs the check against `planted` (JSON is YAML), or a missing file when it is None."""
    path = tmp_path / "planted.yml"
    if planted is not None:
        path.write_text(json.dumps(planted), encoding="utf-8")
    env = {"WORKFLOW": str(path)}
    if advisory is not None:
        env["ADVISORY_JOBS"] = advisory
    return run_step(find_step(workflow, NEEDS_CHECK_STEP), tmp_path, env)


def test_needs_check_passes_on_the_committed_workflow(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    completed = run_step(find_step(workflow, NEEDS_CHECK_STEP), tmp_path, {})
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"({ADVISORY_JOB}): {', '.join(sorted(needed))}." in completed.stdout


def test_expected_jobs_is_the_number_of_needed_jobs(
    workflow: dict[str, Any], needed: list[str]
) -> None:
    assert int(find_step(workflow, CI_STEP)["env"]["EXPECTED_JOBS"]) == len(needed)


def test_the_advisory_list_holds_the_e2e_job_only(workflow: dict[str, Any]) -> None:
    assert find_step(workflow, NEEDS_CHECK_STEP)["env"]["ADVISORY_JOBS"] == ADVISORY_JOB


def test_needs_check_fails_when_ci_does_not_need_a_job(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    planted["jobs"]["ci"]["needs"].remove("compatibility")
    set_expected_jobs(planted, len(planted["jobs"]["ci"]["needs"]))
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert "CI's needs must list every job" in completed.stdout
    assert "< compatibility" in completed.stdout
    assert "EXPECTED_JOBS in the CI job" not in completed.stdout


def test_needs_check_fails_on_a_new_job_ci_does_not_need(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    planted["jobs"]["new-job"] = {"runs-on": "ubuntu-24.04", "steps": [{"run": "true"}]}
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert "< new-job" in completed.stdout


def test_needs_check_fails_when_ci_needs_a_job_that_does_not_exist(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    planted["jobs"]["ci"]["needs"].append("no-such-job")
    set_expected_jobs(planted, len(planted["jobs"]["ci"]["needs"]))
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert "> no-such-job" in completed.stdout
    assert "EXPECTED_JOBS in the CI job" not in completed.stdout


def test_needs_check_fails_when_ci_needs_a_job_twice(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    planted["jobs"]["ci"]["needs"].append("pytest")
    set_expected_jobs(planted, len(planted["jobs"]["ci"]["needs"]))
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert "> pytest" in completed.stdout


def test_needs_check_fails_when_an_advisory_job_is_not_a_job(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    del planted["jobs"][ADVISORY_JOB]
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert f"ADVISORY_JOBS lists {ADVISORY_JOB}, which is not a job" in completed.stdout
    assert "CI's needs must list" not in completed.stdout


def test_needs_check_fails_on_a_stale_advisory_entry(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    advisory = f"{ADVISORY_JOB} gone-job"
    completed = run_needs_check(workflow, tmp_path, copy.deepcopy(workflow), advisory)
    assert completed.returncode == 1
    assert "ADVISORY_JOBS lists gone-job, which is not a job" in completed.stdout


def test_needs_check_fails_on_an_advisory_entry_listed_twice(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    advisory = f"{ADVISORY_JOB} {ADVISORY_JOB}"
    completed = run_needs_check(workflow, tmp_path, copy.deepcopy(workflow), advisory)
    assert completed.returncode == 1
    assert f"ADVISORY_JOBS lists {ADVISORY_JOB} twice" in completed.stdout
    assert "CI's needs must list" not in completed.stdout


def test_needs_check_fails_when_ci_needs_an_advisory_job(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    planted["jobs"]["ci"]["needs"].append(ADVISORY_JOB)
    set_expected_jobs(planted, len(planted["jobs"]["ci"]["needs"]))
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert f"CI needs {ADVISORY_JOB}, which ADVISORY_JOBS" in completed.stdout


def test_needs_check_fails_when_a_job_is_neither_needed_nor_advisory(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    completed = run_needs_check(workflow, tmp_path, copy.deepcopy(workflow), "")
    assert completed.returncode == 1
    assert f"< {ADVISORY_JOB}" in completed.stdout


@pytest.mark.parametrize("delta", [-1, 1])
def test_needs_check_fails_on_a_wrong_expected_jobs(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path, delta: int
) -> None:
    planted = copy.deepcopy(workflow)
    set_expected_jobs(planted, len(needed) + delta)
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert (
        f"EXPECTED_JOBS in the CI job is {len(needed) + delta}, but CI needs {len(needed)} jobs"
    ) in completed.stdout
    assert "CI's needs must list" not in completed.stdout


def test_needs_check_fails_when_ci_has_no_expected_jobs(
    workflow: dict[str, Any], needed: list[str], tmp_path: Path
) -> None:
    planted = copy.deepcopy(workflow)
    find_step(planted, CI_STEP)["name"] = "Renamed"
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 1
    assert f"EXPECTED_JOBS in the CI job is not set, but CI needs {len(needed)}" in (
        completed.stdout
    )


@pytest.mark.parametrize(
    "planted",
    [
        None,
        {},
        {"on": "push"},
        {"jobs": {"ci": {"runs-on": "ubuntu-24.04", "steps": [{"run": "true"}]}}},
    ],
    ids=["missing file", "empty", "no jobs", "only ci"],
)
def test_needs_check_exits_2_when_no_job_is_read(
    workflow: dict[str, Any], tmp_path: Path, planted: dict[str, Any] | None
) -> None:
    completed = run_needs_check(workflow, tmp_path, planted)
    assert completed.returncode == 2
    assert "No jobs read from" in completed.stdout


# --- the local actions' shellcheck in Workflow Hardening ----------------------


def bash_step(name: str, script: str) -> dict[str, str]:
    return {"name": name, "shell": "bash", "run": script}


def run_shellcheck_step(
    workflow: dict[str, Any], tmp_path: Path, actions: dict[str, list[dict[str, str]]]
) -> subprocess.CompletedProcess[str]:
    """Runs the step against planted actions, each a list of composite steps (JSON is YAML)."""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for name, steps in actions.items():
        (actions_dir / name).mkdir()
        action = {"name": name, "runs": {"using": "composite", "steps": steps}}
        (actions_dir / name / "action.yml").write_text(json.dumps(action), encoding="utf-8")
    tool("shellcheck")
    return run_step(
        find_step(workflow, SHELLCHECK_STEP), tmp_path, {"ACTIONS_DIR": str(actions_dir)}
    )


def test_shellcheck_step_passes_on_the_committed_actions(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    tool("shellcheck")
    completed = run_step(find_step(workflow, SHELLCHECK_STEP), tmp_path, {})
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Shellcheck found nothing" in completed.stdout


def test_shellcheck_step_fails_on_a_finding_and_names_its_step(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    actions = {
        "clean": [bash_step("Clean", 'echo "clean"')],
        "mixed": [
            {"name": "Checkout", "uses": "actions/checkout@v7"},
            bash_step("Quoted", 'echo "$HOME"'),
            bash_step("Unquoted", "echo $HOME"),
        ],
    }
    completed = run_shellcheck_step(workflow, tmp_path, actions)
    assert completed.returncode == 1
    assert "SC2086" in completed.stdout
    assert 'Step "Unquoted" has the shellcheck findings above' in completed.stdout
    assert 'Step "Quoted"' not in completed.stdout
    assert 'Step "Clean"' not in completed.stdout


def test_shellcheck_step_reads_expressions_as_placeholders(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    actions = {"expressions": [bash_step("Expression", 'echo "${{ inputs.python-version }}"')]}
    completed = run_shellcheck_step(workflow, tmp_path, actions)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_shellcheck_step_leaves_off_the_checks_actionlint_turns_off(
    workflow: dict[str, Any], tmp_path: Path
) -> None:
    actions = {"env": [bash_step("Variable from env", 'echo "$set_by_env"')]}
    completed = run_shellcheck_step(workflow, tmp_path, actions)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("actions", "error"),
    [
        ({}, "Could not read"),
        ({"uses-only": [{"name": "Checkout", "uses": "actions/checkout@v7"}]}, "No bash step read"),
    ],
    ids=["no action", "no bash step"],
)
def test_shellcheck_step_exits_2_when_no_bash_step_is_read(
    workflow: dict[str, Any],
    tmp_path: Path,
    actions: dict[str, list[dict[str, str]]],
    error: str,
) -> None:
    completed = run_shellcheck_step(workflow, tmp_path, actions)
    assert completed.returncode == 2
    assert f"title=Shellcheck::{error}" in completed.stdout
