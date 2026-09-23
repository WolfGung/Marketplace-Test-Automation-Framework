"""The build script assembles the site, and that is all it does.

`scripts/build-showcase.sh` puts `site/` together -- the Allure report of both
test jobs, the page `showcase/build.py` writes from the same results, the two
diagrams, and the recording and trace of the purchase when the run left them --
and stops. The CI run uploads that directory as a GitHub Pages artifact and
deploys it, so nothing is published from the script and it has no git to do:
no branch, no worktree, no commit, no push. The one thing it reads from outside
the checkout is the previous publication's Allure history, fetched from the
published site (`SITE_URL`), which is what carries the report's trend from one
publication to the next.

The first half of this module reads the file. `showcase.build.PREFERRED_RECORDINGS`
(used by `_pick_video`) is the one place that decides which recording is the
purchase and gets a `<video>` block on the page. A second, independent list of
glob patterns in the shell script -- copying a file `build.py` would not caption
-- is exactly how a real recording was once published while the page never
referenced it (found in review). These tests do not re-implement the selection
rule; they make sure there is nowhere else for a second one to live, and that
the script hands the builder the real videos directory instead of relying on a
default that only happens to be right sometimes.

The second half runs the script against a server on loopback standing in for
the published site, because the two things that matter most cannot be proven by
reading: that the build leaves git exactly as it found it, and what it does with
the history the site sends back -- or does not. No test here reaches the
internet: every proxy setting points at a closed port, so even a script that
ignored `SITE_URL` would fail here instead of fetching the real site.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from showcase.build import PUBLISHED_TRACE_URL

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build-showcase.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _commands() -> list[str]:
    """The script's command lines: its comments explain the rules, its code could break them."""
    return [
        line.strip() for line in _text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# -- the file, read -----------------------------------------------------------


def test_the_script_has_no_hardcoded_video_glob() -> None:
    text = _text()
    assert "*.webm" not in text, (
        "a webm glob literal in the script is a second, independent video "
        "selection rule that showcase/build.py's PREFERRED_RECORDINGS cannot "
        "be kept in step with"
    )
    assert "test_logged_in_user_can_place_an_order" not in text
    assert "test_product_details_match_api_catalog" not in text


def test_the_script_does_not_copy_a_video_itself() -> None:
    """Only `showcase/build.py` may write `site/media/checkout.webm` -- a
    second `cp` to that path from the script would be exactly the
    conflicting write the divergence bug came from. (The path may be named in
    this script's comments explaining why not; only a command line actually
    writing there is disallowed.)"""
    assert not any("media/checkout.webm" in line for line in _commands())


def test_the_script_gives_the_builder_the_real_videos_directory() -> None:
    """`showcase/build.py --videos` must see this run's actual videos
    directory, not its own default, or its own placement (the only one that
    exists) would be wrong too."""
    text = _text()
    assert "showcase/build.py" in text
    assert '--videos "$VIDEOS"' in text


def test_the_script_has_no_hardcoded_trace_glob() -> None:
    """The trace is picked by `showcase.build.PREFERRED_TRACES` for exactly the
    reason the recording is, so the script must not learn to pick one too."""
    assert "*.zip" not in _text()


def test_the_script_gives_the_builder_the_real_traces_directory() -> None:
    assert '--traces "$TRACES"' in _text()


def test_the_script_merges_the_two_jobs_results_through_the_tested_module() -> None:
    """`showcase/merge.py` is what `tests/unit/test_showcase_merge.py`
    actually exercises; the script has to be the one calling it, or that
    coverage says nothing about what ships."""
    text = _text()
    assert "showcase/merge.py categories" in text
    assert "showcase/merge.py environment" in text


def test_the_script_runs_no_git_command() -> None:
    """Nothing is published from the script, so there is nothing for git to do.

    The site used to reach GitHub Pages as a commit that replaced a whole
    branch on every publication. The CI run deploys it as an artifact now, and
    a git command here would be the old mechanism finding its way back. The run
    further down proves the same by watching git; this names the line.
    """
    git = [line for line in _commands() if re.search(r"\bgit\b", line)]
    assert not git, f"the build script runs git: {git}"


def test_the_history_is_read_back_from_the_site_the_page_is_published_at() -> None:
    """One site, named in three places, pinned together.

    The script's `SITE_URL` default is where it reads the previous
    publication's history from, the workflow sets `SITE_URL` for the run that
    deploys, and `showcase.build.PUBLISHED_TRACE_URL` is where the page sends
    the trace viewer for a file this same site serves. Were they to name two
    different sites, the trend would be read from somewhere the report is not
    published, and it would quietly stop at a single run.
    """
    defaults = re.findall(r'SITE_URL="\$\{SITE_URL:-([^}"]+)\}"', _text())
    assert len(defaults) == 1, f"expected one SITE_URL default in the script, found {defaults}"
    site = defaults[0]
    assert site.endswith("/"), f"SITE_URL names a directory and ends in a slash: {site}"
    assert PUBLISHED_TRACE_URL == f"{site}media/checkout-trace.zip"

    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    builds = [step for step in jobs["showcase"]["steps"] if "build-showcase.sh" in step.get("run", "")]
    assert len(builds) == 1, f"expected one step of `showcase` to run the build script, found {len(builds)}"
    assert builds[0]["env"]["SITE_URL"] == site


# -- the script, actually run -------------------------------------------------

#: The history Allure writes beside a report, one file per name, in the shape
#: it writes it: the per-test history is an object keyed by history id, and each
#: of the four trends is an array with an entry per publication.
HISTORY: dict[str, object] = {
    "history": {"api-case": {"statistic": {"passed": 1, "total": 1}, "items": [{"uid": "a", "status": "passed"}]}},
    "history-trend": [{"data": {"passed": 24, "total": 24}}],
    "duration-trend": [{"data": {"duration": 41_287}}],
    "categories-trend": [{"data": {}}],
    "retry-trend": [{"data": {"run": 24, "retry": 0}}],
}

#: Stands in for the Allure command line. What the report holds is not what
#: these tests are about, and a real one would need a JVM to prove a shell
#: script. It writes a page wherever `-o` points and keeps a copy of the history
#: it was handed, which is how a test knows the history was in place *before*
#: the report was generated, rather than merely somewhere by the end.
_FAKE_ALLURE = """#!/bin/sh
out=""
results=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift ;;
    generate|--clean) ;;
    *) results="$1" ;;
  esac
  shift
done
mkdir -p "$out" "$ALLURE_SAW"
echo "<!doctype html><title>report</title>" > "$out/index.html"
if [ -d "$results/history" ]; then
  cp "$results/history/"* "$ALLURE_SAW/" 2>/dev/null || true
fi
"""

#: Reaching npx would mean downloading Allure from npm in the middle of a test.
_NO_NPX = """#!/bin/sh
echo "npx was called: these tests hand the script its Allure through ALLURE_BIN" >&2
exit 97
"""

#: Every name a proxy setting goes by, in lower case; each also has an upper-case
#: twin. The script tests point all of them at a closed port, loopback exempt.
_PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


def _executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _closed_port() -> int:
    """A port on loopback nobody listens on: a connection to it is refused at once."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _offline_environment() -> dict[str, str]:
    """This environment, with every way out of the machine closed but loopback."""
    env = {
        name: value for name, value in os.environ.items()
        if name.lower() not in _PROXY_VARIABLES
        and name not in {"SITE_URL", "ALLURE_BIN", "RESET_SHOWCASE_HISTORY"}
        and not name.startswith("GIT_")
    }
    dead = f"http://127.0.0.1:{_closed_port()}"
    for name in ("http_proxy", "https_proxy", "all_proxy"):
        env[name] = env[name.upper()] = dead
    env["no_proxy"] = env["NO_PROXY"] = "127.0.0.1,localhost"
    return env


@dataclass
class PublishedSite:
    """The stand-in for the published site: lay files out, point the script at it, see what it asked for."""

    root: Path
    url: str
    requested: list[str]

    def publish(self, path: str, body: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


@pytest.fixture
def published_site(tmp_path: Path) -> Iterator[PublishedSite]:
    """A static server on loopback over an empty directory: a file answers 200, anything else 404."""
    root = tmp_path / "published-site"
    root.mkdir()
    requested: list[str] = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            requested.append(self.path)
            super().do_GET()

        def log_message(self, *args: object) -> None:
            """Quiet: a test states what it expected to be asked instead."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield PublishedSite(root=root, url=f"http://127.0.0.1:{server.server_address[1]}/", requested=requested)
    finally:
        server.shutdown()
        server.server_close()


def _result(layer: str) -> dict:
    """One passed case of one layer: what `showcase/build.py` needs to count a run."""
    return {
        "uuid": f"{layer}-0000",
        "historyId": f"{layer}-case",
        "name": f"a {layer} case",
        "fullName": f"tests.{layer}.test_case#a_{layer}_case",
        "status": "passed",
        "start": 1_758_400_000_000,
        "stop": 1_758_400_001_000,
        "labels": [{"name": "tag", "value": layer}],
    }


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A scratch copy of what the build reads: the script, `showcase/` and both jobs' results.

    The build runs here rather than in this repository, so a test never
    touches the `site/` or `allure-results/` of the checkout it runs from.
    """
    repo = tmp_path / "checkout"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
    shutil.copytree(ROOT / "showcase", repo / "showcase", ignore=shutil.ignore_patterns("__pycache__"))
    for job, layer in (("allure-results-api", "api"), ("allure-results-ui", "ui")):
        results = repo / job
        results.mkdir()
        (results / f"{layer}-result.json").write_text(json.dumps(_result(layer)), encoding="utf-8")
        (results / "categories.json").write_text('[{"name": "Product defects"}]', encoding="utf-8")
        (results / "environment.properties").write_text(f"{layer}.Python=3.12\n", encoding="utf-8")
    return repo


@pytest.fixture
def tools(tmp_path: Path) -> Path:
    """What the script finds first on PATH: a fake Allure, a refusing npx, and this interpreter."""
    directory = tmp_path / "tools"
    directory.mkdir()
    _executable(directory / "allure", _FAKE_ALLURE)
    _executable(directory / "npx", _NO_NPX)
    for name in ("python", "python3"):
        _executable(directory / name, f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    return directory


@pytest.fixture
def build(checkout: Path, tools: Path, tmp_path: Path) -> Callable[..., subprocess.CompletedProcess]:
    """Run the build the way CI does, against the site at `site_url`."""

    def run(site_url: str, **extra_env: str) -> subprocess.CompletedProcess:
        env = _offline_environment()
        env.update(
            PATH=f"{tools}{os.pathsep}{env.get('PATH', '')}",
            ALLURE_BIN=str(tools / "allure"),
            ALLURE_SAW=str(tmp_path / "allure-saw"),
            SITE_URL=site_url,
        )
        env.update(extra_env)
        return subprocess.run(
            ["bash", "scripts/build-showcase.sh", "allure-results-api", "allure-results-ui", "videos", "traces"],
            cwd=checkout, capture_output=True, text=True, env=env, timeout=120,
        )

    return run


def _served() -> dict[str, str]:
    return {name: json.dumps(value) for name, value in HISTORY.items()}


def _publish_history(site: PublishedSite, bodies: dict[str, str]) -> None:
    for name, body in bodies.items():
        site.publish(f"report/history/{name}.json", body)


def _saw(tmp_path: Path) -> dict[str, str]:
    """The history Allure was handed when it ran, by file name, as it was written there."""
    saw = tmp_path / "allure-saw"
    if not saw.is_dir():
        return {}
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(saw.iterdir())}


def _git(*args: str, cwd: Path) -> str:
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env).stdout


def _git_state(repo: Path) -> dict[str, str]:
    """Everything a publication would have to change: refs, HEAD, worktrees and every object."""
    return {
        "refs": _git("for-each-ref", "--format=%(refname) %(objectname)", cwd=repo),
        "head": _git("symbolic-ref", "-q", "HEAD", cwd=repo) + _git("rev-parse", "-q", "--verify", "HEAD", cwd=repo),
        "worktrees": _git("worktree", "list", "--porcelain", cwd=repo),
        "objects": _git("cat-file", "--batch-all-objects", "--batch-check", cwd=repo),
    }


def test_the_build_leaves_no_branch_worktree_or_commit_and_never_pushes(
    checkout: Path, build, tools: Path, published_site: PublishedSite, tmp_path: Path
) -> None:
    """Exercised rather than read: a build that publishes nothing writes nothing to git.

    Both switches that let the old script push are set -- `GITHUB_ACTIONS`,
    which every CI job carries, and the explicit `PUBLISH_SHOWCASE` -- and the
    checkout has an `origin` this process could certainly push to. `git` is
    wrapped so every call is written down: the build may make none, least of
    all a push. Refs, HEAD, worktrees and every object, reachable or not, are
    the same afterwards in the checkout and in `origin`; what the build leaves
    behind is the site.
    """
    origin = tmp_path / "origin.git"
    _git("init", "-q", "--bare", str(origin), cwd=tmp_path)
    _git("init", "-q", "-b", "main", cwd=checkout)
    _git("add", "-A", cwd=checkout)
    _git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "-qm", "the checkout the build runs in", cwd=checkout)
    _git("remote", "add", "origin", str(origin), cwd=checkout)
    assert _git("rev-parse", "--verify", "HEAD", cwd=checkout), "precondition: the checkout has a commit"
    before = {"checkout": _git_state(checkout), "origin": _git_state(origin)}

    calls = tmp_path / "git-calls.log"
    _executable(tools / "git", f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{calls}"\nexec "{shutil.which("git")}" "$@"\n')
    result = build(published_site.url, GITHUB_ACTIONS="true", PUBLISH_SHOWCASE="1")

    assert result.returncode == 0, result.stderr
    made = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    assert not [call for call in made if call.split()[:1] == ["push"]], f"the build pushed: {made}"
    assert made == [], f"the build ran git, which it has no reason to do: {made}"
    assert {"checkout": _git_state(checkout), "origin": _git_state(origin)} == before
    site = checkout / "site"
    for built in ("index.html", "report/index.html", "assets/architecture.svg", "assets/ci-pipeline.svg"):
        assert (site / built).is_file(), f"site/{built} was not assembled"
    assert (site / ".nojekyll").is_file()


def test_the_published_history_is_in_place_before_the_report_is_generated(
    checkout: Path, build, published_site: PublishedSite, tmp_path: Path
) -> None:
    """All five of Allure's history files come down from `SITE_URL`, byte for
    byte, into the results the report is generated from -- and they are there
    when Allure runs. The report goes to `site/report`, which is where the next
    build will ask for its history."""
    served = _served()
    _publish_history(published_site, served)

    result = build(published_site.url)

    assert result.returncode == 0, result.stderr
    assert _saw(tmp_path) == {f"{name}.json": body for name, body in served.items()}
    assert sorted(published_site.requested) == sorted(f"/report/history/{name}.json" for name in HISTORY)
    assert (checkout / "site" / "report" / "index.html").is_file()
    assert (checkout / "site" / "index.html").is_file()


def test_an_address_without_its_trailing_slash_reaches_the_same_history(
    build, published_site: PublishedSite, tmp_path: Path
) -> None:
    """`SITE_URL` names a directory. Written without its last slash, a path
    joined onto it would land beside the site instead of inside it, and the
    trend would be lost to a typo; the script puts the slash back."""
    _publish_history(published_site, _served())

    result = build(published_site.url.rstrip("/"))

    assert result.returncode == 0, result.stderr
    assert set(_saw(tmp_path)) == {f"{name}.json" for name in HISTORY}


def test_a_history_file_that_is_not_json_is_left_out(
    build, published_site: PublishedSite, tmp_path: Path
) -> None:
    """A body that does not parse -- a page served with a 200 where the file
    should be, a download cut short -- is not history, and it is not handed to
    Allure as if it were. The files that did arrive whole still carry the trend,
    and the log names the ones left out."""
    served = _served()
    served["history-trend"] = "<!doctype html><title>Site not found</title>"
    served["duration-trend"] = '[{"data": {"duration": 41'
    _publish_history(published_site, served)

    result = build(published_site.url)

    assert result.returncode == 0, result.stderr
    kept = {"history", "categories-trend", "retry-trend"}
    assert _saw(tmp_path) == {f"{name}.json": served[name] for name in kept}
    assert "history-trend.json" in result.stderr
    assert "duration-trend.json" in result.stderr


def test_a_history_file_of_the_wrong_shape_is_left_out(
    build, published_site: PublishedSite, tmp_path: Path
) -> None:
    """Parsing is not enough. `null` is valid JSON, and Allure 2.30.0 stops
    with a NullPointerException when that is what `history.json` holds -- the
    whole publication would be lost to one bad file. So a file whose top level
    is not what Allure writes there is refused like one that does not parse."""
    served = _served()
    served["history"] = "null"
    served["retry-trend"] = '{"data": {"run": 24, "retry": 0}}'
    _publish_history(published_site, served)

    result = build(published_site.url)

    assert result.returncode == 0, result.stderr
    assert set(_saw(tmp_path)) == {"history-trend.json", "duration-trend.json", "categories-trend.json"}
    assert "/history.json" in result.stderr
    assert "retry-trend.json" in result.stderr


def test_a_first_publication_builds_without_a_trend(
    checkout: Path, build, published_site: PublishedSite, tmp_path: Path
) -> None:
    """The very first publication has nothing to carry over: every file is a
    404. That is not a failure -- the report shows this run alone, and the log
    says why rather than leaving it to be noticed on the chart."""
    result = build(published_site.url)

    assert result.returncode == 0, result.stderr
    assert _saw(tmp_path) == {}
    assert "no Allure history" in result.stderr
    assert (checkout / "site" / "index.html").is_file()
    assert (checkout / "site" / "report" / "index.html").is_file()


def test_an_unreachable_site_means_no_trend_and_the_build_goes_on(
    checkout: Path, build, tmp_path: Path
) -> None:
    """A runner that cannot reach the site at all still builds the page: the
    trend starts again from this run, and the log says the site did not
    answer."""
    result = build(f"http://127.0.0.1:{_closed_port()}/")

    assert result.returncode == 0, result.stderr
    assert _saw(tmp_path) == {}
    assert "did not answer" in result.stderr
    assert (checkout / "site" / "index.html").is_file()
    assert (checkout / "site" / "report" / "index.html").is_file()


def test_starting_the_trend_over_asks_the_site_for_nothing(
    build, published_site: PublishedSite, tmp_path: Path
) -> None:
    """`RESET_SHOWCASE_HISTORY` is the documented, off-by-default way to
    discard the published trend on purpose, for exactly one publication. Set,
    it carries none of that history over, and does not even ask for it."""
    _publish_history(published_site, _served())

    result = build(published_site.url, RESET_SHOWCASE_HISTORY="1")

    assert result.returncode == 0, result.stderr
    assert _saw(tmp_path) == {}
    assert published_site.requested == []
