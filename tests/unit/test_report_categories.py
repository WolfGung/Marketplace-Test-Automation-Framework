"""The report's failure grouping ships with the results, or it does not happen."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_categories_file_is_valid_and_declares_statuses() -> None:
    payload = json.loads((ROOT / "allure" / "categories.json").read_text(encoding="utf-8"))
    assert payload, "categories.json is empty"
    for category in payload:
        assert category.get("name"), "a category without a name explains nothing"
        assert category.get("matchedStatuses"), f"{category['name']} matches no status"


def test_selector_category_is_listed_before_timeouts() -> None:
    """Allure files a result under the first category that matches.

    A Playwright locator timeout's trace contains both `TimeoutError` and
    `waiting for locator`, so whichever of these two categories comes first
    in the file wins for every one of them. A locator that timed out is
    usually markup that moved, not a slow network, so "Selector no longer
    matches" must be listed first — otherwise it can never win a single
    result and its name is a lie.
    """
    payload = json.loads((ROOT / "allure" / "categories.json").read_text(encoding="utf-8"))
    names = [category["name"] for category in payload]
    assert names.index("Selector no longer matches") < names.index("Timeouts")


def test_categories_reach_the_results_directory(tmp_path) -> None:
    from tests.conftest import copy_categories_into

    copy_categories_into(tmp_path)
    assert (tmp_path / "categories.json").is_file()


def _keys(results_dir) -> set[str]:
    written = (results_dir / "environment.properties").read_text(encoding="utf-8")
    return {line.split("=", 1)[0] for line in written.splitlines() if line}


def test_environment_properties_names_what_a_reader_needs(tmp_path, monkeypatch) -> None:
    """The Environment panel is only useful if it names the run's actual context.

    This is the shape outside CI, where nothing qualifies the keys -- so the
    variable that would qualify them has to be cleared rather than assumed
    absent. It is set for every step of every GitHub Actions job, including the
    one that runs this suite, and a test that reads the ambient environment
    passes or fails on where it happens to be run.
    """
    from tests.conftest import _write_environment_properties

    monkeypatch.delenv("GITHUB_JOB", raising=False)
    _write_environment_properties(tmp_path, browser_used=True)

    assert _keys(tmp_path) == {"BASE_URL", "API_BASE_URL", "Browser", "Headless", "Python", "CI"}


def test_a_run_that_opens_no_browser_does_not_report_one(tmp_path, monkeypatch) -> None:
    """`Settings.browser` and `Settings.headless` always hold a value, because
    they have defaults. The `api` job never opens a browser, so writing them
    from its session put `api.Browser=chromium` in front of a reader as a fact
    about a job that launched nothing."""
    from tests.conftest import _write_environment_properties

    monkeypatch.delenv("GITHUB_JOB", raising=False)
    _write_environment_properties(tmp_path, browser_used=False)

    assert _keys(tmp_path) == {"BASE_URL", "API_BASE_URL", "Python", "CI"}


def test_environment_properties_are_qualified_by_job_in_ci(tmp_path, monkeypatch) -> None:
    """Two CI jobs write this file under the same name; a merge downstream
    (`showcase/merge.py`) can only union them instead of colliding if each
    job's keys say which job they came from."""
    from tests.conftest import _write_environment_properties

    monkeypatch.setenv("GITHUB_JOB", "ui")
    _write_environment_properties(tmp_path, browser_used=True)

    assert _keys(tmp_path) == {
        "ui.BASE_URL",
        "ui.API_BASE_URL",
        "ui.Browser",
        "ui.Headless",
        "ui.Python",
        "ui.CI",
    }


def test_whether_a_browser_is_opened_is_read_off_the_fixture_closure() -> None:
    """The fact the panel now depends on has to be read from the session, not
    guessed from a marker: `browser` is a session fixture that `page` requires
    and every page object fixture requires in turn, so a case reaches it
    however it was selected."""
    from tests.conftest import _will_drive_a_browser

    class _Item:
        def __init__(self, *fixtures: str) -> None:
            self.fixturenames = list(fixtures)

    assert _will_drive_a_browser([_Item("page", "context", "browser")])
    assert not _will_drive_a_browser([_Item("http_client", "products_api")])
    assert not _will_drive_a_browser([])


def test_a_missing_categories_file_warns_but_does_not_abort_the_session(tmp_path, monkeypatch) -> None:
    """A checkout without `allure/categories.json` still runs its tests.

    The report comes out plainer (no Categories tab), which is a fair trade
    against not running at all — but the run has to say so, not swallow it.
    """
    import tests.conftest as conftest

    monkeypatch.setattr(conftest, "CATEGORIES", tmp_path / "does-not-exist.json")
    results_dir = tmp_path / "results"

    with pytest.warns(UserWarning, match="categories.json"):
        conftest._prepare_reporting(results_dir, browser_used=False)  # must not raise

    assert not (results_dir / "categories.json").exists()
    # the environment write is independent and must still have happened
    assert (results_dir / "environment.properties").is_file()


def test_a_broken_environment_write_warns_but_does_not_abort_the_session(tmp_path, monkeypatch) -> None:
    """Settings blowing up must not cost the categories file too."""
    import tests.conftest as conftest

    def _boom() -> None:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(conftest, "get_settings", _boom)
    results_dir = tmp_path / "results"

    with pytest.warns(UserWarning, match="environment.properties"):
        conftest._prepare_reporting(results_dir, browser_used=False)  # must not raise

    assert (results_dir / "categories.json").is_file()
    assert not (results_dir / "environment.properties").exists()


def test_an_unwritable_results_directory_does_not_abort_the_session(tmp_path) -> None:
    """The same failure class as a full disk: the path exists but isn't a directory."""
    import tests.conftest as conftest

    blocked = tmp_path / "blocked"
    blocked.write_text("occupies the path a results directory needs")

    with pytest.warns(UserWarning):
        conftest._prepare_reporting(blocked, browser_used=False)  # must not raise


class _FakeOption:
    def __init__(self, collectonly: bool) -> None:
        self.collectonly = collectonly


class _FakeConfig:
    def __init__(self, *, collectonly: bool, alluredir: str | None) -> None:
        self.option = _FakeOption(collectonly)
        self._alluredir = alluredir

    def getoption(self, name: str, default: str | None = None) -> str | None:
        assert name == "--alluredir"
        return self._alluredir if self._alluredir is not None else default


class _FakeSession:
    def __init__(self, config: _FakeConfig, items: list | None = None) -> None:
        self.config = config
        self.items = items if items is not None else []


class _BrowserItem:
    fixturenames = ["page", "context", "browser"]


def _record(monkeypatch, conftest) -> list[tuple[Path, bool]]:
    calls: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        conftest,
        "_prepare_reporting",
        lambda results_dir, *, browser_used: calls.append((results_dir, browser_used)),
    )
    return calls


def test_collection_skips_reporting_on_collect_only(monkeypatch, tmp_path) -> None:
    import tests.conftest as conftest

    calls = _record(monkeypatch, conftest)
    config = _FakeConfig(collectonly=True, alluredir=str(tmp_path))
    conftest.pytest_collection_finish(_FakeSession(config))  # type: ignore[arg-type]

    assert calls == []


def test_collection_skips_reporting_without_alluredir(monkeypatch) -> None:
    import tests.conftest as conftest

    calls = _record(monkeypatch, conftest)
    config = _FakeConfig(collectonly=False, alluredir=None)
    conftest.pytest_collection_finish(_FakeSession(config))  # type: ignore[arg-type]

    assert calls == []


def test_collection_prepares_reporting_when_alluredir_is_set(monkeypatch, tmp_path) -> None:
    """And hands on what the collected items say about a browser, which is the
    fact the Environment panel now reports rather than assumes."""
    import tests.conftest as conftest

    calls = _record(monkeypatch, conftest)
    target = tmp_path / "results"
    config = _FakeConfig(collectonly=False, alluredir=str(target))
    conftest.pytest_collection_finish(  # type: ignore[arg-type]
        _FakeSession(config, [_BrowserItem()]),
    )

    assert calls == [(target, True)]


#: The mini-suite below is the CI command's shape in miniature: a marked case
#: that needs no browser, a marked case that needs one, and this project's own
#: conftest supplying both the hook under test and the fixtures.
_MINI_CONFTEST = "from tests.conftest import *  # noqa: F401,F403\n"
_MINI_API = "import pytest\n\n\n@pytest.mark.api\ndef test_asks_no_browser():\n    assert True\n"
_MINI_UI = "import pytest\n\n\n@pytest.mark.ui\ndef test_needs_a_browser(page):\n    assert page\n"


def test_a_marker_selection_decides_the_panel_not_the_whole_collection(tmp_path) -> None:
    """`pytest -m api` collects the browser cases and then deselects them.

    This is the failure that shipped: read from `pytest_collection_modifyitems`
    in a conftest, `items` still holds every case pytest collected, because
    that hook is called before the deselection. The CI job would then write
    `api.Browser=chromium` again, from a session that opens nothing -- and
    with only the unit-level tests above, all of which hand the hook a list
    directly, nothing would have noticed. So this one runs pytest.
    """
    import subprocess
    import sys

    (tmp_path / "conftest.py").write_text(_MINI_CONFTEST, encoding="utf-8")
    (tmp_path / "test_api_like.py").write_text(_MINI_API, encoding="utf-8")
    (tmp_path / "test_ui_like.py").write_text(_MINI_UI, encoding="utf-8")
    results = tmp_path / "results"

    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-m", "api", "-q",
            "-p", "no:cacheprovider", f"--alluredir={results}", str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": f"{ROOT}{os.pathsep}{ROOT / 'src'}",
            "GITHUB_JOB": "api",
        },
        timeout=120,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "1 deselected" in proc.stdout, (
        f"precondition: the browser case has to be collected and then deselected, "
        f"which is the whole shape being tested.\n{proc.stdout}"
    )

    assert _keys(results) == {
        "api.BASE_URL", "api.API_BASE_URL", "api.Python", "api.CI",
    }
