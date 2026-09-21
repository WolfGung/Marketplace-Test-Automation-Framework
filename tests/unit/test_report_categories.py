"""The report's failure grouping ships with the results, or it does not happen."""
from __future__ import annotations

import json
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


def test_environment_properties_names_what_a_reader_needs(tmp_path) -> None:
    """The Environment panel is only useful if it names the run's actual context."""
    from tests.conftest import _write_environment_properties

    _write_environment_properties(tmp_path)

    written = (tmp_path / "environment.properties").read_text(encoding="utf-8")
    keys = {line.split("=", 1)[0] for line in written.splitlines() if line}
    assert keys == {"BASE_URL", "API_BASE_URL", "Browser", "Headless", "Python", "CI"}


def test_a_missing_categories_file_warns_but_does_not_abort_the_session(tmp_path, monkeypatch) -> None:
    """A checkout without `allure/categories.json` still runs its tests.

    The report comes out plainer (no Categories tab), which is a fair trade
    against not running at all — but the run has to say so, not swallow it.
    """
    import tests.conftest as conftest

    monkeypatch.setattr(conftest, "CATEGORIES", tmp_path / "does-not-exist.json")
    results_dir = tmp_path / "results"

    with pytest.warns(UserWarning, match="categories.json"):
        conftest._prepare_reporting(results_dir)  # must not raise

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
        conftest._prepare_reporting(results_dir)  # must not raise

    assert (results_dir / "categories.json").is_file()
    assert not (results_dir / "environment.properties").exists()


def test_an_unwritable_results_directory_does_not_abort_the_session(tmp_path) -> None:
    """The same failure class as a full disk: the path exists but isn't a directory."""
    import tests.conftest as conftest

    blocked = tmp_path / "blocked"
    blocked.write_text("occupies the path a results directory needs")

    with pytest.warns(UserWarning):
        conftest._prepare_reporting(blocked)  # must not raise


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
    def __init__(self, config: _FakeConfig) -> None:
        self.config = config


def test_sessionstart_skips_reporting_on_collect_only(monkeypatch, tmp_path) -> None:
    import tests.conftest as conftest

    calls: list[Path] = []
    monkeypatch.setattr(conftest, "_prepare_reporting", calls.append)

    session = _FakeSession(_FakeConfig(collectonly=True, alluredir=str(tmp_path)))
    conftest.pytest_sessionstart(session)  # type: ignore[arg-type]

    assert calls == []


def test_sessionstart_skips_reporting_without_alluredir(monkeypatch) -> None:
    import tests.conftest as conftest

    calls: list[Path] = []
    monkeypatch.setattr(conftest, "_prepare_reporting", calls.append)

    session = _FakeSession(_FakeConfig(collectonly=False, alluredir=None))
    conftest.pytest_sessionstart(session)  # type: ignore[arg-type]

    assert calls == []


def test_sessionstart_prepares_reporting_when_alluredir_is_set(monkeypatch, tmp_path) -> None:
    import tests.conftest as conftest

    calls: list[Path] = []
    monkeypatch.setattr(conftest, "_prepare_reporting", calls.append)

    target = tmp_path / "results"
    session = _FakeSession(_FakeConfig(collectonly=False, alluredir=str(target)))
    conftest.pytest_sessionstart(session)  # type: ignore[arg-type]

    assert calls == [target]
