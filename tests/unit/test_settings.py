"""The video switch is environment-driven like every other setting."""
from __future__ import annotations

import pytest

from ecom_taf.config.settings import Settings


@pytest.mark.parametrize("raw, expected", [("true", True), ("1", True), ("false", False)])
def test_record_video_reads_the_environment(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("RECORD_VIDEO", raw)
    assert Settings().record_video is expected


def test_record_video_is_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("RECORD_VIDEO", raising=False)
    assert Settings().record_video is False
