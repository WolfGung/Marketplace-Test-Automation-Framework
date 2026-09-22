"""The pipeline runs the suite against the stand and touches the public site in one job only."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
JOBS = WORKFLOW["jobs"]
PUBLIC_SITE = "automationexercise.com"

#: The selection that makes the drift check safe to point at somebody else's
#: site: the smoke set minus everything that creates an account or places an
#: order. It is also how that step is found below, because a step's position in
#: a list is not a fact about the step -- a cache step inserted above it would
#: move the old `steps[-2]` onto the upload, and the check would then read an
#: environment that is not there without ever saying it had lost the step.
SMOKE_SELECTION = '-m "smoke and not destructive"'


def _run_lines(job: dict) -> str:
    """Everything a job runs, and everything it is handed while running it.

    A workflow names its target in two places, and reading only one of them is
    what lets the other change unnoticed: `run:` is the command, and `env:` --
    on the job, or on a single step -- is the configuration that command reads.
    This suite takes its target from the environment, so `BASE_URL:
    https://somebody-elses-site` on a step points a job at that site exactly as
    surely as typing the address into the command, and a reader that looked
    only at `run:` would call the job local.

    Both are stringified rather than walked: the question is whether a name
    appears anywhere in what the job executes or is given, and a YAML mapping
    rendered as text answers it without this having to know the shape of every
    value GitHub Actions allows.
    """
    parts = [str(job.get("env", ""))]
    for step in job["steps"]:
        parts.append(step.get("run", ""))
        parts.append(str(step.get("env", "")))
    return "\n".join(parts)


def _needs(job: dict) -> list[str]:
    """A job's `needs`, always as a list.

    GitHub Actions accepts one dependency written bare (`needs: reachable`) and
    several as a list, and both are ordinary. Comparing the raw value against a
    string passes for the list form without looking inside it, so
    `needs: [reachable]` would have satisfied "this job does not wait for the
    probe" while waiting for exactly that.
    """
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def _step_running(job: dict, fragment: str, job_name: str) -> dict:
    """The one step of a job whose command contains `fragment`."""
    matching = [step for step in job["steps"] if fragment in step.get("run", "")]
    assert len(matching) == 1, (
        f"expected exactly one step of the `{job_name}` job to run `{fragment}`, "
        f"found {len(matching)}. Either the step stopped running that selection or "
        f"another one started running it too, and in both cases what this test "
        f"checks is no longer where it thinks it is."
    )
    return matching[0]


def test_only_the_external_job_and_the_probe_name_the_public_site() -> None:
    naming = {name for name, job in JOBS.items() if PUBLIC_SITE in _run_lines(job)}
    assert naming == {"reachable"}, naming
    drift = _step_running(JOBS["external"], SMOKE_SELECTION, "external")
    assert drift["env"]["TEST_ENV"] == "prod"


def test_the_external_job_runs_only_the_non_destructive_smoke_set_and_never_blocks() -> None:
    job = JOBS["external"]
    assert job["continue-on-error"] is True
    assert SMOKE_SELECTION in _run_lines(job)
    assert _needs(job) == ["reachable"]
    assert "showcase" in JOBS and "external" not in _needs(JOBS["showcase"])


def test_the_stand_jobs_do_not_wait_for_the_probe() -> None:
    for name in ("api", "ui", "browsers"):
        assert "reachable" not in _needs(JOBS[name]), name
        assert "reachable" not in str(JOBS[name].get("if", "")), name
