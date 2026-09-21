"""The report's failure grouping ships with the results, or it does not happen."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_categories_file_is_valid_and_declares_statuses() -> None:
    payload = json.loads((ROOT / "allure" / "categories.json").read_text(encoding="utf-8"))
    assert payload, "categories.json is empty"
    for category in payload:
        assert category.get("name"), "a category without a name explains nothing"
        assert category.get("matchedStatuses"), f"{category['name']} matches no status"


def test_categories_reach_the_results_directory(tmp_path, pytestconfig) -> None:
    from tests.conftest import copy_categories_into

    copy_categories_into(tmp_path)
    assert (tmp_path / "categories.json").is_file()
