"""The failure-diagnostics capture is a guard, not a reporter: it must never raise."""
from __future__ import annotations

from typing import Any

import allure
import pytest

from tests.conftest import _capture_failure_diagnostics


class _RaisingPage:
    """Stands in for a closed/dead Playwright page: both captures fail."""

    def screenshot(self, *, full_page: bool, timeout: int) -> bytes:
        raise RuntimeError("screenshot boom")

    def content(self) -> str:
        raise RuntimeError("content boom")


def test_failed_captures_attach_an_explanation_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attached: list[tuple[Any, str, Any]] = []

    def fake_attach(body: Any, *, name: str, attachment_type: Any) -> None:
        attached.append((body, name, attachment_type))

    monkeypatch.setattr(allure, "attach", fake_attach)

    _capture_failure_diagnostics(_RaisingPage())  # must not raise

    names = [name for _, name, _ in attached]
    assert names == ["failure-screenshot-unavailable", "failure-html-unavailable"]
    assert "screenshot boom" in attached[0][0]
    assert "content boom" in attached[1][0]


def test_a_broken_allure_attach_does_not_take_the_capture_down_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_attach(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("allure is down")

    monkeypatch.setattr(allure, "attach", failing_attach)

    with pytest.warns(UserWarning):
        _capture_failure_diagnostics(_RaisingPage())  # must not raise even here
