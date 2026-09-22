"""Every count the figures state about the suite is a count pytest collects.

The two diagrams on the showcase page quote numbers — how many cases each
layer holds, how many carry a marker, how many the browser job runs — and
nobody notices a drawing going stale. A client reads the figure in a few
seconds and never checks it against the repository, so a case added tomorrow
has to fail the build here rather than quietly make a picture lie.

Three kinds of source state those counts today: the two hand-drawn SVG figures
on the showcase page, showcase/assets/cover.html -- the template the image the
profile shows is exported from -- and the coverage table in README.md, which is
the second thing a reader of this project sees after the published page. Each
kind is read the way it is written, and each count is pinned against the
selection it claims to describe: some are a directory's whole collection, some
are their sum, and the smoke count is a marker that cuts across all of them.
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
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "showcase" / "assets"
SVG = "{http://www.w3.org/2000/svg}"
FIGURES = ("architecture.svg", "ci-pipeline.svg")

#: The template `guru-cover-image.png` is exported from. It is in this list for
#: the same reason the figures are, and more urgently: the cover is the first
#: thing a client sees, it is a picture rather than text, and nobody re-reads a
#: picture to check whether it still adds up.
COVER = "cover.html"

#: The coverage table in the README. It is in this list because the README is
#: the second most-read thing this project has, it is the one source of these
#: counts that lives outside showcase/assets, and it is the easiest of the
#: three to edit without thinking about the suite.
README = "README.md"
SOURCES = (*FIGURES, COVER, README)

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
    ".html": (
        "The cover is exported from showcase/assets/{source}, so edit the number "
        "there and export again -- the image is not edited by hand:\n"
        "  pytest -q --alluredir=allure-results\n"
        "  ~/.local/bin/allure generate allure-results --clean -o site/report\n"
        "  PYTHONPATH=. python scripts/make-assets.py\n"
        "then `git add guru-cover-image.png`: the exported image is a tracked file, "
        "and a template nobody exported changes nothing the profile shows."
    ),
    ".md": (
        "The count is a cell in the coverage table under `## Coverage` in {source}: "
        "edit it there. If a test really was added or removed, the figures under "
        "showcase/assets/ state the same counts and need the new number too."
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
    # The cover's three cards are the three test directories, one per card, and
    # they are counted the same way the architecture figure counts them.
    (COVER, "REST API"): ("-m", "", "tests/api"),
    (COVER, "Browser"): ("-m", "", "tests/ui"),
    (COVER, "End-to-end"): ("-m", "", "tests/e2e"),
    # The badge is not a fourth layer. Its first number is what the three cards
    # add up to -- the checks of the application, which is every case outside
    # tests/unit, where the suite checks itself rather than the marketplace --
    # and its second is a marker that cuts across all three.
    (COVER, "automated checks"): ("-m", "", "tests/api", "tests/ui", "tests/e2e"),
    (COVER, "of them in the smoke set"): ("-m", "smoke"),
    # The README's table says the same things in the same order, plus one the
    # page states in prose rather than in a figure: the checks of the framework
    # itself, which are every case in tests/unit and are counted apart from the
    # marketplace because they prove nothing about it.
    (README, "The REST API"): ("-m", "", "tests/api"),
    (README, "The browser"): ("-m", "", "tests/ui"),
    (README, "End to end, across both doors"): ("-m", "", "tests/e2e"),
    (README, "The application under test"): ("-m", "", "tests/api", "tests/ui", "tests/e2e"),
    (README, "Of those, the smoke set"): ("-m", "smoke"),
    (README, "The framework itself"): ("-m", "", "tests/unit"),
}


def _path(source: str) -> str:
    """Where a source lives, for a message someone has to act on."""
    if source == README:
        return README
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


#: Elements HTML closes on your behalf. A stack waiting for their end tag
#: would never unwind, and every count after the first `<meta>` would be read
#: as if it sat inside it.
VOID_ELEMENTS = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)


class _Stats(HTMLParser):
    """The counts a cover template states, read out of the markup it renders.

    The same idea as `_drawn`, in the medium the cover is written in: a count
    is not listed in a table kept beside the file, it is found in the file. An
    element with class `stat` is one stated count; the number is the element
    with class `stat-n` inside it and the label a reader sees beside that
    number is the element with class `stat-of`. Both are visible text, so what
    this finds is what the exported image shows -- a number moved into the
    wrong card, or a card left with a number and no label, is a failure here
    rather than something plausible nobody looks at twice.
    """

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        self._open: list[dict] = []
        self.found: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID_ELEMENTS:
            return
        classes = set((dict(attrs).get("class") or "").split())
        self._open.append({"tag": tag, "classes": classes, "text": [], "roles": {}})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """`<path/>` and the rest of the inline SVG open and close at once."""

    def handle_data(self, data: str) -> None:
        if self._open:
            self._open[-1]["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        # Unwinds to the tag that closed rather than assuming the markup is
        # balanced: one unclosed element should cost its own count, not every
        # count after it.
        while self._open:
            frame = self._open.pop()
            self._finish(frame)
            if frame["tag"] == tag:
                return

    def close(self) -> None:
        super().close()
        while self._open:
            self._finish(self._open.pop())

    def _finish(self, frame: dict) -> None:
        """Hand one closed element's text and roles up to the one holding it."""
        text = " ".join("".join(frame["text"]).split())
        roles = frame["roles"]
        if "stat-n" in frame["classes"]:
            roles.setdefault("n", text)
        if "stat-of" in frame["classes"]:
            roles.setdefault("of", text)
        if "stat" in frame["classes"]:
            self._record(roles, text)
            roles = {}  # a stated count is closed; it is not part of an outer one
        if self._open:
            parent = self._open[-1]
            parent["text"].append(text)
            for role, value in roles.items():
                parent["roles"].setdefault(role, value)

    def _record(self, roles: dict[str, str], text: str) -> None:
        missing = sorted({"n": "stat-n", "of": "stat-of"}[k] for k in ("n", "of") if k not in roles)
        assert not missing, (
            f"{_path(self._source)}: the count reading \"{text}\" has no "
            f"{' and no '.join(missing)}. An element with class `stat` states one "
            f"count, and has to hold both the number and the label it is shown under."
        )
        number, label = roles["n"], roles["of"]
        assert number.isdigit(), (
            f'{_path(self._source)}: the count shown under "{label}" is {number!r}, '
            f"which is not a number."
        )
        assert label not in self.found, (
            f'{_path(self._source)}: two counts are shown under "{label}". A label is '
            f"what this test looks a count up by, so two of them cannot share one."
        )
        self.found[label] = int(number)


@cache
def _stated(cover: str) -> dict[str, int]:
    """Every count a cover template states, keyed by the label beside it."""
    parser = _Stats(cover)
    parser.feed((ASSETS / cover).read_text(encoding="utf-8"))
    parser.close()
    assert parser.found, (
        f"{_path(cover)} states no counts at all: nothing in it carries the `stat`, "
        f"`stat-n` and `stat-of` classes this test reads. Either the cover stopped "
        f"quoting numbers, or it was rewritten in a way this reader no longer "
        f"understands -- in which case the numbers on the image the profile shows "
        f"are no longer checked by anything."
    )
    return parser.found


#: The heading the coverage table sits under, and the one that ends it. Reading
#: only that section keeps this from finding a number in some other table --
#: the configuration table's defaults, say -- and calling it a case count.
COVERAGE_HEADING = "## Coverage"

#: One row of a Markdown table: three cells between four pipes. A row whose
#: middle cell is not a number is not a stated count -- the header row and the
#: `| --- |` separator are both rows -- so those are passed over rather than
#: guessed at.
TABLE_ROW = re.compile(r"^\|(?P<label>[^|]*)\|(?P<count>[^|]*)\|(?P<where>[^|]*)\|$")

#: Markdown a cell can be dressed in without changing the words a reader sees.
CELL_DRESSING = re.compile(r"[`*]")


def _plain(cell: str) -> str:
    """One table cell as a reader sees it, with the Markdown taken off."""
    return " ".join(CELL_DRESSING.sub("", cell).split())


def _coverage_section(markdown: str, source: str) -> str:
    """The `## Coverage` section of a Markdown document, heading excluded."""
    start = markdown.find(COVERAGE_HEADING)
    assert start != -1, (
        f'{source} has no "{COVERAGE_HEADING}" section, so the coverage table '
        f"this test reads is not where it was. Either the heading was renamed -- "
        f"fix COVERAGE_HEADING here -- or the table is gone, in which case the "
        f"README no longer states the counts and these claims should go with it."
    )
    body = markdown[start + len(COVERAGE_HEADING):]
    end = body.find("\n## ")
    return body if end == -1 else body[:end]


def _table_counts(markdown: str, source: str) -> dict[str, int]:
    """Every count the coverage table states, keyed by the label beside it.

    The same idea as `_drawn` and `_Stats`, in the medium a README is written
    in: the pairing is read out of the document rather than out of a table kept
    beside it. A row states one count -- what is being counted, the number, and
    where a reader can count it themselves -- and it is the first two cells
    that are pinned here.
    """
    found: dict[str, int] = {}
    for line in _coverage_section(markdown, source).splitlines():
        row = TABLE_ROW.match(line.strip())
        if row is None:
            continue
        count = _plain(row["count"])
        if not count.isdigit():
            continue
        label = _plain(row["label"])
        assert label, (
            f"{source}: the coverage table has a row stating {count} with nothing "
            f"in its first cell. A row's label is what this test looks its count "
            f"up by, so a count with no label is a number nobody can check."
        )
        assert label not in found, (
            f'{source}: the coverage table states two counts for "{label}". A '
            f"label is what this test looks a count up by, so two rows cannot "
            f"share one."
        )
        found[label] = int(count)
    return found


def _require_counts(found: dict[str, int], source: str) -> dict[str, int]:
    """Refuse an empty reading instead of passing it on.

    Every claim is checked against what the reader finds, so a reader that came
    back empty from a rewritten README would report success over a document
    stating nothing at all. This is the one place that says no.
    """
    assert found, (
        f"{source} states no counts at all: nothing under "
        f'"{COVERAGE_HEADING}" is a table row whose second cell is a number. '
        f"Either the table stopped quoting counts, or it was rewritten in a way "
        f"this reader no longer understands -- in which case the numbers the "
        f"README shows are no longer checked by anything."
    )
    return found


@cache
def _tabled(source: str) -> dict[str, int]:
    """Every count the README's coverage table states."""
    text = (ROOT / source).read_text(encoding="utf-8")
    return _require_counts(_table_counts(text, _path(source)), _path(source))


def _drawn_source(source: str) -> dict[str, int]:
    """Every count `source` states, dispatched by how that kind is written."""
    suffix = Path(source).suffix
    if suffix == ".md":
        return _tabled(source)
    if suffix == ".html":
        return _stated(source)
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


# The reader above is the only thing standing between the README's table and a
# number nobody checks. These three hold it to reading what is written: a count
# it finds, a reading it must refuse, and the real table with one digit changed.

def test_the_table_reader_reads_the_counts_a_row_states() -> None:
    """A row is a label and a number, whatever Markdown it is dressed in."""
    found = _table_counts(
        "## Coverage\n"
        "\n"
        "| What is checked | Checks | Where |\n"
        "| --- | --- | --- |\n"
        "| The REST API | 14 | `tests/api` |\n"
        "| **The application under test** | **24** | the rows above |\n"
        "\n"
        "## Configuration\n"
        "\n"
        "| `HEADLESS` | 1 | not a case count, and in another section |\n",
        "a document written for this test",
    )
    assert found == {"The REST API": 14, "The application under test": 24}


def test_a_table_the_reader_cannot_read_fails_instead_of_finding_nothing() -> None:
    """A reading that matched nothing is a failure, not a pass over an empty set."""
    silent = _table_counts("## Coverage\n\nThe counts moved into a picture.\n", README)
    assert silent == {}, "precondition: this document states no counts the reader can see"
    with pytest.raises(AssertionError, match="no counts at all"):
        _require_counts(silent, README)


def test_a_number_changed_in_the_table_is_one_this_test_would_catch() -> None:
    """The pin bites: the reader reads the digits on the page, not a constant."""
    label = "The REST API"
    selection = CLAIMS[(README, label)]
    stated = _tabled(README)[label]
    assert stated == _collected(selection), "precondition: the README is right today"

    text = (ROOT / README).read_text(encoding="utf-8")
    tampered_text = text.replace(f"| {label} | {stated} |", f"| {label} | {stated + 1} |", 1)
    assert tampered_text != text, (
        f'no row reading "| {label} | {stated} |" is in {README}: this test edits the '
        f"table as it is written, so a table written differently needs it rewritten too"
    )
    tampered = _table_counts(tampered_text, _path(README))
    assert tampered[label] == stated + 1, (
        "the reader did not see the changed digit, so it is not reading the table"
    )
    assert tampered[label] != _collected(selection)
