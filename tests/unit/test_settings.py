"""Settings read the environment, and a named target never overrules what somebody set."""
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

    An example may be commented out, and two of them are. `BASE_URL` and
    `API_BASE_URL` override the target `TEST_ENV` selects, and a copied
    `.env` that sets them to the stand's address would pin every run to that
    address -- including the drift check, which is `TEST_ENV=prod` and nothing
    else. So they are shown as commented examples: a reader sees the name, the
    shape of the value and the sentence saying what setting it does, and a
    plain `cp .env.example .env` still follows `TEST_ENV`. A commented example
    is still an example, so it counts here.
    """
    expected = {
        ALIASES.get(field, field.upper()) for field in Settings.model_fields
    }

    tabled = _documented("## Configuration", (ROOT / "README.md").read_text(encoding="utf-8"))
    example = set(re.findall(
        r"^(?:#\s*)?(\w+)=", (ROOT / ".env.example").read_text(encoding="utf-8"), re.M
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


# `environments.yaml` holds an address per named target, and `TEST_ENV` picks
# one. It is a default, not an override: the three cases below are the value
# somebody passed, the value a `.env` file sets -- the one that used to be
# discarded, because a dotenv value never reaches `os.environ` -- and the value
# nobody set anywhere, which is the only one the named target fills in.


def test_a_value_the_caller_set_survives_the_named_environment(monkeypatch) -> None:
    """A target is a default. What somebody actually set wins over it."""
    monkeypatch.setenv("TEST_ENV", "local")
    # Both are cleared, and `_env_file` is switched off, so what comes out is
    # what this test set and what the target filled in -- not what the machine
    # running it happens to export. The container does export them: compose
    # points the suite at the stand service by address.
    for name in ("BASE_URL", "API_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(base_url="http://127.0.0.1:8099", _env_file=None)

    settings.apply_named_environment()

    assert settings.base_url == "http://127.0.0.1:8099"
    # The other half of the pair is untouched by the caller, so the target
    # still fills that one in: this overrules a value, it does not switch the
    # named environment off.
    assert settings.api_base_url == "http://127.0.0.1:8092/api"


def test_a_value_a_dotenv_file_sets_survives_the_named_environment(monkeypatch, tmp_path) -> None:
    """The bug this guards: `.env` was read and then silently thrown away.

    The setup instructions say `cp .env.example .env`, and the old check was
    `"BASE_URL" not in os.environ` — which a dotenv value is never in, because
    pydantic-settings reads the file itself. So every address a reader put in
    that file was overwritten by the target's own, with nothing said. The file
    here is a temporary one rather than the repository's: whether this passes
    must not depend on whether the machine running it happens to have a `.env`.
    """
    monkeypatch.setenv("TEST_ENV", "local")
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("API_BASE_URL", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("BASE_URL=http://127.0.0.1:8099\n", encoding="utf-8")

    settings = Settings(_env_file=str(dotenv))
    assert "base_url" in settings.model_fields_set, "precondition: the file was read at all"

    settings.apply_named_environment()

    assert settings.base_url == "http://127.0.0.1:8099"


def test_a_setting_nobody_set_follows_the_named_environment(monkeypatch) -> None:
    """`TEST_ENV=prod` resolves to the public site, and resolving is all this does.

    No request is made here and none is wanted: the drift check is the one job
    that talks to somebody else's site, and this is about which strings the
    settings come out holding.
    """
    monkeypatch.setenv("TEST_ENV", "prod")
    for name in ("BASE_URL", "API_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)
    settings.apply_named_environment()

    assert settings.base_url == "https://www.automationexercise.com"
    assert settings.api_base_url == "https://www.automationexercise.com/api"
