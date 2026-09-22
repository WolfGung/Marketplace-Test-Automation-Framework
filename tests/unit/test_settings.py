"""The video switch is environment-driven like every other setting."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ecom_taf.config.settings import Settings

ROOT = Path(__file__).resolve().parents[2]

#: The one setting whose environment name is not its field name upper-cased.
#: `env` is read through `validation_alias="TEST_ENV"`, because `ENV` on its
#: own says nothing in a shell that already has a hundred variables in it.
ALIASES = {"env": "TEST_ENV"}


@pytest.mark.parametrize("raw, expected", [("true", True), ("1", True), ("false", False)])
def test_record_video_reads_the_environment(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("RECORD_VIDEO", raw)
    assert Settings().record_video is expected


def test_record_video_is_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("RECORD_VIDEO", raising=False)
    assert Settings().record_video is False


def _documented(section: str, text: str) -> set[str]:
    """The variable names a README section states, read out of its table."""
    body = text.split(section, 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `(\w+)` \|", body, re.M))


def test_every_setting_is_documented_and_has_an_example() -> None:
    """A setting nobody can find is a setting nobody uses.

    Both lists went stale the same way: `RECORD_VIDEO` was being used in the
    README's own "Run tests" block thirty lines above a configuration table
    that had never heard of it, and `.env.example` — the file the setup
    instructions tell a reader to copy — was missing it too, along with
    `VIDEO_DIR`, `TRACE_DIR` and `TEST_ENV`. Reading the three from the files
    themselves is what keeps a setting added tomorrow from being private to
    whoever added it.
    """
    expected = {
        ALIASES.get(field, field.upper()) for field in Settings.model_fields
    }

    tabled = _documented("## Configuration", (ROOT / "README.md").read_text(encoding="utf-8"))
    example = set(re.findall(
        r"^(\w+)=", (ROOT / ".env.example").read_text(encoding="utf-8"), re.M
    ))

    assert tabled == expected, (
        "the README's configuration table and Settings disagree: "
        f"undocumented {sorted(expected - tabled)}, "
        f"documented but not a setting {sorted(tabled - expected)}"
    )
    assert example == expected, (
        ".env.example and Settings disagree: "
        f"missing {sorted(expected - example)}, "
        f"not a setting {sorted(example - expected)}"
    )
