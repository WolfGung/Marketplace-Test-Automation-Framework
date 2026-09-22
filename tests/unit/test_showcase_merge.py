"""Merging two CI jobs' Allure results must not silently drop either one's.

`categories.json` and `environment.properties` are the two fixed-name files
each job writes into its own `--alluredir` (see `tests/conftest.py`). Copying
both jobs' results into one directory by filename -- the way an artefact
download naturally would -- lets the second copy win over the first without
a trace. `showcase/merge.py` is what the publish step actually calls instead;
these tests are the ones that would fail if it went back to silently
preferring one side.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from showcase.merge import merge_categories, merge_environment_properties


def test_categories_from_a_single_source_is_used_as_is(tmp_path: Path) -> None:
    source = tmp_path / "api" / "categories.json"
    source.parent.mkdir()
    source.write_text('[{"name": "Timeouts"}]', encoding="utf-8")

    target = tmp_path / "merged" / "categories.json"
    merge_categories([source], target)

    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_identical_categories_from_both_jobs_merge_without_complaint(tmp_path: Path) -> None:
    payload = '[{"name": "Timeouts"}]'
    api = tmp_path / "api" / "categories.json"
    ui = tmp_path / "ui" / "categories.json"
    for source in (api, ui):
        source.parent.mkdir()
        source.write_text(payload, encoding="utf-8")

    target = tmp_path / "merged" / "categories.json"
    merge_categories([api, ui], target)

    assert target.read_text(encoding="utf-8") == payload


def test_categories_that_disagree_between_jobs_stop_the_merge(tmp_path: Path) -> None:
    api = tmp_path / "api" / "categories.json"
    ui = tmp_path / "ui" / "categories.json"
    api.parent.mkdir()
    ui.parent.mkdir()
    api.write_text('[{"name": "Timeouts"}]', encoding="utf-8")
    ui.write_text('[{"name": "Something else"}]', encoding="utf-8")

    with pytest.raises(ValueError, match="categories.json differs"):
        merge_categories([api, ui], tmp_path / "merged" / "categories.json")


def test_a_missing_categories_source_is_not_an_error(tmp_path: Path) -> None:
    """Neither job is guaranteed to have written one (see
    `test_a_missing_categories_file_warns_but_does_not_abort_the_session`)."""
    target = tmp_path / "merged" / "categories.json"
    merge_categories([tmp_path / "does-not-exist.json"], target)
    assert not target.exists()


def test_environment_properties_from_both_jobs_are_unioned(tmp_path: Path) -> None:
    api = tmp_path / "api" / "environment.properties"
    ui = tmp_path / "ui" / "environment.properties"
    api.parent.mkdir()
    ui.parent.mkdir()
    api.write_text("api.Browser=none\napi.Headless=True", encoding="utf-8")
    ui.write_text("ui.Browser=chromium\nui.Headless=True", encoding="utf-8")

    target = tmp_path / "merged" / "environment.properties"
    merge_environment_properties([api, ui], target)

    written = target.read_text(encoding="utf-8")
    lines = set(written.splitlines())
    assert lines == {"api.Browser=none", "api.Headless=True", "ui.Browser=chromium", "ui.Headless=True"}


def test_the_same_key_and_value_in_both_jobs_is_not_a_collision(tmp_path: Path) -> None:
    api = tmp_path / "api" / "environment.properties"
    ui = tmp_path / "ui" / "environment.properties"
    api.parent.mkdir()
    ui.parent.mkdir()
    api.write_text("Python=3.12.5", encoding="utf-8")
    ui.write_text("Python=3.12.5", encoding="utf-8")

    target = tmp_path / "merged" / "environment.properties"
    merge_environment_properties([api, ui], target)

    assert target.read_text(encoding="utf-8").splitlines() == ["Python=3.12.5"]


def test_an_unqualified_key_that_disagrees_between_jobs_is_loud_not_silent(tmp_path: Path) -> None:
    """The realistic way to hit this: results written outside CI, where
    `tests/conftest.py` does not qualify keys by job at all."""
    api = tmp_path / "api" / "environment.properties"
    ui = tmp_path / "ui" / "environment.properties"
    api.parent.mkdir()
    ui.parent.mkdir()
    api.write_text("Browser=none", encoding="utf-8")
    ui.write_text("Browser=chromium", encoding="utf-8")

    with pytest.raises(ValueError, match="environment.properties key 'Browser' disagrees"):
        merge_environment_properties([api, ui], tmp_path / "merged" / "environment.properties")


def test_a_missing_environment_properties_source_is_not_an_error(tmp_path: Path) -> None:
    ui = tmp_path / "ui" / "environment.properties"
    ui.parent.mkdir()
    ui.write_text("ui.Browser=chromium", encoding="utf-8")

    target = tmp_path / "merged" / "environment.properties"
    merge_environment_properties([tmp_path / "api" / "environment.properties", ui], target)

    assert target.read_text(encoding="utf-8").splitlines() == ["ui.Browser=chromium"]


def test_no_sources_at_all_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "merged" / "environment.properties"
    merge_environment_properties([tmp_path / "does-not-exist.properties"], target)
    assert not target.exists()
