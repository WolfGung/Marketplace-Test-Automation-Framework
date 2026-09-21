"""Every count the figures state about the suite is a count pytest collects.

The two diagrams on the showcase page quote numbers — how many cases each
layer holds, how many carry a marker, how many the browser job runs — and
nobody notices a drawing going stale. A client reads the figure in a few
seconds and never checks it against the repository, so a case added tomorrow
has to fail the build here rather than quietly make a picture lie.

The figures are the only sources this module reads today. The cover image and
the README quote the same counts and are written in later steps of this plan;
each adds its own reader and its own lines in CLAIMS.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "showcase" / "assets"
SVG = "{http://www.w3.org/2000/svg}"
FIGURES = ("architecture.svg", "ci-pipeline.svg")
SOURCES = FIGURES

#: "14 cases", and "1 case" where a figure has to say it — the integration
#: marker is on exactly one test, and "1 cases" would be a drawing nobody
#: would ship.
DRAWN_COUNT = re.compile(r"^(\d+) cases?$")

#: Collection normally finishes in a fraction of a second (see `_collected`);
#: this is generous enough never to fire on a merely slow machine, so a hit
#: here means the subprocess actually hung.
COLLECT_TIMEOUT_SECONDS = 60

#: What to do when a count no longer matches, per kind of source. Later steps
#: of this plan add an exported image and the README, which are fixed in
#: different ways — hence a table rather than one sentence.
FIX = {
    ".svg": (
        "The figure is hand-drawn SVG: edit the number in showcase/assets/{source}. "
        "Both figures quote counts, so check the other one too."
    ),
}
FIX_DEFAULT = "Edit the number in {source} to match what pytest collects."

# Every count a figure states, with the selection it claims to describe.
# ``-m ""`` selects nothing away, which is what a box titled with a directory
# claims: every case in that directory, marked or not. The marker chips and the
# pipeline's two suites are selections instead, and are written as the command
# a reader can run. Adding a count to a figure without adding it here fails the
# last test in this module.
CLAIMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("architecture.svg", "tests/api"): ("-m", "", "tests/api"),
    ("architecture.svg", "tests/ui"): ("-m", "", "tests/ui"),
    ("architecture.svg", "tests/e2e"): ("-m", "", "tests/e2e"),
    ("architecture.svg", "smoke"): ("-m", "smoke"),
    ("architecture.svg", "negative"): ("-m", "negative"),
    ("architecture.svg", "integration"): ("-m", "integration"),
    ("ci-pipeline.svg", "API suite"): ("-m", "api"),
    ("ci-pipeline.svg", "browser suite"): ("-m", "ui or e2e"),
}


def _path(source: str) -> str:
    """Where a source lives, for a message someone has to act on."""
    return f"showcase/assets/{source}"


@cache
def _drawn(figure: str) -> dict[str, int]:
    """Every case count in a figure, keyed by the title of the box holding it.

    Both the boxes and the text are in the file with their coordinates, so the
    pairing is read out of the drawing itself rather than out of a table kept
    beside it: a text belongs to the box it sits inside, and a box's title is
    its topmost line. A number moved into the wrong box, or a box left with a
    number and no title, is therefore visible here rather than plausible.
    """
    tree = ET.parse(ASSETS / figure)
    boxes = [
        (float(r.get("x")), float(r.get("y")), float(r.get("width")), float(r.get("height")))
        for r in tree.iter(f"{SVG}rect")
        if "box" in (r.get("class") or "")
    ]
    lines: dict[tuple[float, float, float, float], list[tuple[float, str]]] = {}
    for text in tree.iter(f"{SVG}text"):
        x, y = float(text.get("x")), float(text.get("y"))
        for box in boxes:
            left, top, width, height = box
            if left <= x <= left + width and top <= y <= top + height:
                lines.setdefault(box, []).append((y, (text.text or "").strip()))
                break

    drawn: dict[str, int] = {}
    for _box, contents in lines.items():
        contents.sort()
        bodies = [body for _, body in contents]
        counts = [int(m.group(1)) for m in map(DRAWN_COUNT.match, bodies) if m]
        if not counts:
            continue
        assert len(counts) == 1, f"{figure}: two case counts in one box: {bodies}"
        drawn[bodies[0]] = counts[0]
    return drawn


def _drawn_source(source: str) -> dict[str, int]:
    """Every count `source` states, dispatched by how that kind is written."""
    return _drawn(source)


@cache
def _collected(selection: tuple[str, ...]) -> int:
    """How many tests pytest collects for one selection, counted from node ids.

    Collection runs in a subprocess for two reasons. It is the command the
    failure message tells a reader to run, so what this test checks and what
    they can reproduce by hand are the same thing; and importing the suite in
    the session that is already running it would re-enter this module's own
    collection. The spool directory keeps any future `--alluredir` in
    `addopts` from writing into the results the showcase page is built from.
    It costs about a fifth of a second and is cached per selection.
    """
    with tempfile.TemporaryDirectory() as spool:
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest", "--collect-only", "-q",
                    "-p", "no:cacheprovider", f"--alluredir={spool}", *selection,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{ROOT}"},
                timeout=COLLECT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(
                f"pytest --collect-only {shlex.join(selection)} did not finish "
                f"within {COLLECT_TIMEOUT_SECONDS}s, waiting on collection that "
                f"normally takes a fraction of a second — this is a hang, not a "
                f"slow machine.\nstdout so far: {exc.stdout!r}\n"
                f"stderr so far: {exc.stderr!r}"
            )
    ids = [
        line for line in proc.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    assert ids, (
        f"pytest {shlex.join(selection)} collected nothing, so this test cannot "
        f"check anything.\n{proc.stdout}\n{proc.stderr}"
    )
    return len(ids)


@pytest.mark.parametrize(("source", "box"), list(CLAIMS), ids=lambda v: v)
def test_a_figure_states_the_number_of_cases_pytest_collects(source: str, box: str) -> None:
    selection = CLAIMS[(source, box)]
    drawn = _drawn_source(source).get(box)
    assert drawn is not None, (
        f'{_path(source)} no longer states a count under "{box}". Either the box '
        f"was renamed, in which case fix CLAIMS in this file, or the count was "
        f"dropped from the drawing."
    )
    collected = _collected(selection)
    assert drawn == collected, (
        f'{_path(source)} states {drawn} for "{box}", but pytest collects '
        f"{collected}: `pytest {shlex.join(selection)}`.\n"
        f"A test was added, removed or re-marked. "
        + FIX.get(Path(source).suffix, FIX_DEFAULT).format(source=source)
    )


def test_every_case_count_a_figure_states_is_checked() -> None:
    """Without this, a loose reading of the files would pass by finding nothing."""
    drawn = {(source, box) for source in SOURCES for box in _drawn_source(source)}
    assert drawn == set(CLAIMS), (
        "the case counts found in the showcase figures do not match the ones "
        f"this test checks.\n  found:   {sorted(drawn)}\n"
        f"  checked: {sorted(CLAIMS)}\n"
        "A count added to a figure needs a line in CLAIMS naming the pytest "
        "selection it describes; if nothing was found at all, the figures or "
        "the way this test reads them have changed."
    )
