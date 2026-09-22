"""The pipeline runs the suite against the stand and touches the public site in one job only."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
JOBS = WORKFLOW["jobs"]
PUBLIC_SITE = "automationexercise.com"


def _run_lines(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_only_the_external_job_and_the_probe_name_the_public_site() -> None:
    naming = {
        name
        for name, job in JOBS.items()
        if PUBLIC_SITE in _run_lines(job) or PUBLIC_SITE in str(job.get("env", ""))
    }
    assert naming == {"reachable"}, naming
    assert JOBS["external"]["steps"][-2]["env"]["TEST_ENV"] == "prod"


def test_the_external_job_runs_only_the_non_destructive_smoke_set_and_never_blocks() -> None:
    job = JOBS["external"]
    assert job["continue-on-error"] is True
    assert '-m "smoke and not destructive"' in _run_lines(job)
    assert job["needs"] == "reachable"
    assert "showcase" in JOBS and "external" not in JOBS["showcase"]["needs"]


def test_the_stand_jobs_do_not_wait_for_the_probe() -> None:
    for name in ("api", "ui", "browsers"):
        assert JOBS[name].get("needs") != "reachable", name
        assert "reachable" not in str(JOBS[name].get("if", "")), name
