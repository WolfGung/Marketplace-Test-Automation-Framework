"""The install line a reader copies buys everything the suite needs to collect.

The Setup block in the README is the first command anybody runs here, and it
was installing `.[dev]` while the suite could not so much as collect without
`.[stand]`: `tests/stand/conftest.py` imports `fastapi.testclient`,
`tests/stand/test_pages_contract.py` imports `selectolax`, and the
`local_stand` fixture in `tests/conftest.py` imports uvicorn and
`stand.app.main`. A first run that ends in a collection error is a first
impression nobody recovers from, so the extras a reader is told to install are
pinned against the extras `make install` uses -- the one install line in this
repository that is executed rather than read.

Superset rather than equality on purpose. The Makefile is what CI and the
maintainer run, so it is the floor; a README that told a reader to install
*more* than that (a future `docs` extra, say) is generous, not wrong. Less is
the failure this pin exists for.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: An editable install with extras, however it is spelled: `pip install`,
#: `python3 -m pip install`, quoted or not. The extras themselves are the
#: capture -- everything between the brackets.
INSTALL = re.compile(r"pip install\s+-e\s+[\"']?\.\[(?P<extras>[^\]]+)\][\"']?")


def _section(markdown: str, heading: str) -> str:
    """One `## ` section of a Markdown document, heading excluded."""
    start = markdown.find(heading)
    assert start != -1, f"the README no longer has a {heading!r} section"
    body = markdown[start + len(heading):]
    end = body.find("\n## ")
    return body if end == -1 else body[:end]


def _extras(command: str, source: str) -> tuple[str, set[str]]:
    """The extras one install command asks for, and the command as written."""
    match = INSTALL.search(command)
    assert match is not None, (
        f"{source} no longer contains an editable install with extras "
        f"(`pip install -e \".[...]\"`), which is what this pin compares. Either "
        f"the instructions changed shape -- fix INSTALL here -- or one of the two "
        f"stopped installing this project at all."
    )
    return match.group(0), {extra.strip() for extra in match["extras"].split(",")}


def test_the_readme_installs_at_least_what_make_install_does() -> None:
    """A reader who follows Setup can collect the suite; `make install` is the floor."""
    readme_line, readme_extras = _extras(
        _section((ROOT / "README.md").read_text(encoding="utf-8"), "## Setup"),
        "the README's Setup block",
    )
    make_line, make_extras = _extras(
        (ROOT / "Makefile").read_text(encoding="utf-8"),
        "the Makefile's install target",
    )
    assert make_extras <= readme_extras, (
        "the README's Setup block installs less than `make install` does, so a "
        "reader who follows it cannot even collect the suite:\n"
        f"  README:   {readme_line}\n"
        f"  Makefile: {make_line}\n"
        f"missing from the README: {sorted(make_extras - readme_extras)}"
    )
