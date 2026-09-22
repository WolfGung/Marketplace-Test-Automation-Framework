"""The failure-diagnostics capture is a guard, not a reporter: it must never raise."""
from __future__ import annotations

from typing import Any

import allure
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.conftest import _capture_failure_diagnostics


class _RaisingPage:
    """Stands in for a closed/dead Playwright page: both captures fail."""

    def screenshot(self, *, full_page: bool, timeout: int) -> bytes:
        raise RuntimeError("screenshot boom")

    def content(self) -> str:
        raise RuntimeError("content boom")


class _HungPage(_RaisingPage):
    """A page whose main thread is blocked: the screenshot times out.

    `content()` is recorded rather than made to hang, because it has no
    timeout of its own in this Playwright version -- calling it for real here
    would make this test hang exactly the way the guard exists to prevent.
    """

    def __init__(self) -> None:
        self.content_was_called = False

    def screenshot(self, *, full_page: bool, timeout: int) -> bytes:
        raise PlaywrightTimeoutError(f"Timeout {timeout}ms exceeded.")

    def content(self) -> str:
        self.content_was_called = True
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


def test_a_timed_out_screenshot_skips_the_unboundable_html_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`page.content()` takes no timeout argument, and nothing else bounds it
    either in this Playwright version -- `set_default_timeout` does not reach
    it. So a screenshot that times out is treated as a canary: the page cannot
    be trusted to serialise its DOM quickly either, and `content()` must not
    be attempted at all, or this diagnostic could reproduce the very hang it
    exists to catch."""
    attached: list[tuple[Any, str, Any]] = []

    def fake_attach(body: Any, *, name: str, attachment_type: Any) -> None:
        attached.append((body, name, attachment_type))

    monkeypatch.setattr(allure, "attach", fake_attach)
    page = _HungPage()

    _capture_failure_diagnostics(page)  # must not raise, must not hang

    assert page.content_was_called is False
    names = [name for _, name, _ in attached]
    assert names == ["failure-screenshot-unavailable", "failure-html-skipped"]
    assert "timed out" in attached[1][0]
