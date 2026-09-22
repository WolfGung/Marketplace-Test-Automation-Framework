"""The failure-diagnostics capture is a guard, not a reporter: it must never raise."""
from __future__ import annotations

from typing import Any

import allure
import pytest

from tests.conftest import _capture_failure_diagnostics


class _RaisingPage:
    """Stands in for a closed/dead Playwright page: both captures fail."""

    def __init__(self) -> None:
        self.default_timeout_ms: int | None = None

    def screenshot(self, *, full_page: bool, timeout: int) -> bytes:
        raise RuntimeError("screenshot boom")

    def set_default_timeout(self, timeout: float) -> None:
        self.default_timeout_ms = int(timeout)

    def content(self) -> str:
        raise RuntimeError("content boom")


class _SlowPage(_RaisingPage):
    """A page whose HTML capture would hang: it records what bounded it."""

    def content(self) -> str:
        assert self.default_timeout_ms is not None, "content() ran with no bound on it"
        return "<html></html>"


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


def test_the_html_capture_is_bounded_like_the_screenshot_beside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`page.content()` takes no timeout argument, so an unbounded call waits
    out the suite's ordinary navigation timeout on a page already known to be
    in trouble -- on top of the failure being reported. The screenshot was cut
    to five seconds for that reason; this closes the same gap on the capture
    next to it."""
    from tests.conftest import DIAGNOSTIC_CAPTURE_TIMEOUT_MS

    monkeypatch.setattr(allure, "attach", lambda *a, **k: None)
    page = _SlowPage()

    _capture_failure_diagnostics(page)

    assert page.default_timeout_ms == DIAGNOSTIC_CAPTURE_TIMEOUT_MS
