"""Render the portfolio images from their sources.

Editing the wording on a cover should be editing a line of text, not opening
an image editor, so the cover is HTML and this script is the exporter. The
report screenshot comes from the real thing — a generated Allure report served
over HTTP — so refreshing it is re-running this script instead of letting it
age into a lie.

The profile banner is not part of this repository. It is a profile-level
asset that lives with the profile, not with any one project.

Three things this script refuses to do, because each fails silently otherwise:

* photograph an Allure report that is not a complete, passing run. It reads
  the overview's own JSON and compares it with what pytest collects, and says
  what it found when they disagree;
* photograph a pipeline run that is not green. A picture of a run page is a
  claim that the pipeline passes, so the claim is read off the page — the
  status the run shows a visitor, and what every job icon drawn beside it
  says — rather than taken on the word of whoever chose the URL;
* leave behind a blank image. Every export is measured back out of the file
  and out of the pixels the browser actually produced, so a template that
  rendered to an empty field is an error rather than a committed picture of
  nothing.

Usage:
    ~/.local/bin/allure generate allure-results --clean -o site/report
    PYTHONPATH=. python scripts/make-assets.py

The pipeline picture comes from the network and the other two from this
machine, so each is asked for on its own — refreshing the run photograph does
not need a report generated locally first:

    PYTHONPATH=. python scripts/make-assets.py --only ci-run --ci-run <run page>

where <run page> is https://github.com/<owner>/<repo>/actions/runs/<id>.

A run that skipped part of the suite has to say so, or the completeness check
above would reject a report that is exactly what was asked for:

    pytest -m "not e2e" -q --alluredir=allure-results
    ~/.local/bin/allure generate allure-results --clean -o site/report
    PYTHONPATH=. python scripts/make-assets.py --ran "not e2e"

The HTTP server is this script's own: Allure's report reads its data with
`fetch`, which a `file://` page is not allowed to do, and the pixel check
below reads a canvas back, which needs the image to share an origin with the
page reading it. It listens on the loopback interface, on a port the kernel
picks, and it is rooted at the generated report — not at the repository, and
not at the repository behind a rule about how a request is spelled. The
images it also offers back are named under `/exports/`, never walked to.
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# Sized to what the profile expects; anything else is cropped by it.
SHOTS = [
    ("showcase/assets/cover.html", "guru-cover-image.png", 1536, 1024),
]

# The report finishes itself after load: Allure draws the overview charts in
# script. So the page waits for something it only shows once it is ready, then
# gets a moment to settle.
PAGES = [
    ("/", "allure-report-screenshot.png", "text=test cases", 1536, 1024),
]

REPORT_DIR = ROOT / "site" / "report"

#: The pipeline, photographed rather than described. The badge at the top of
#: the README is an image served by somebody else and says one word; the run
#: page it points at is the evidence, and a reader who is deciding in half a
#: minute whether to keep reading will look at a picture of it and not follow
#: a link. It is read logged out, because that is how a visitor reads it.
CI_RUN_IMAGE = "showcase/images/ci-run.png"

#: The window the run page is read in. At this width it lays the job graph out
#: beside the job list, which is the arrangement worth photographing; much
#: narrower and the graph folds underneath.
CI_RUN_VIEWPORT = (1400, 1200)

#: What is kept of that window: the run page's own content, starting below the
#: marketing header a logged-out visitor is served, which says nothing about
#: this pipeline. The size is fixed so the picture is the same shape every
#: time and can be pinned; the job icons are checked to be inside it, so a run
#: that grew another job is a refusal rather than a row sliced in half.
CI_RUN_SIZE = (1400, 900)

#: What a job icon is allowed to say for the run to be worth photographing.
#: GitHub writes each job's state into the icon's accessible name, so this is
#: the picture read the way a screen reader would announce it. `skipped` is in
#: here because this pipeline skips jobs on purpose — the cross-browser suite
#: waits to be asked for — and a skipped job is drawn as such.
GREEN_JOB_STATES = frozenset({"completed successfully", "skipped"})

#: The word a run page shows under "Status" for a run that passed.
GREEN_RUN_STATUS = "Success"

#: How long the run page is given to draw itself. It arrives as an application
#: and fills in afterwards, over somebody else's network.
CI_RUN_TIMEOUT_SECONDS = 60

#: The pictures this script can take, named for `--only`. The cover and the
#: report are exported from what is on this machine; the pipeline is read off
#: a public page.
COVER_SHOT, REPORT_SHOT, CI_RUN_SHOT = "cover", "report", "ci-run"
EVERY_PICTURE = (COVER_SHOT, REPORT_SHOT, CI_RUN_SHOT)
LOCAL_PICTURES = frozenset({COVER_SHOT, REPORT_SHOT})

#: A flat field is one colour everywhere. Real output is not: the cover is a
#: gradient under type, and the report is a white page under a dark sidebar
#: and a chart. Both thresholds sit far below what either produces and far
#: above what an empty page does, so they separate the two cases without
#: being a second opinion on the design.
MIN_DISTINCT_COLOURS = 24
MIN_INK_SHARE = 0.02

#: The pixel probe samples a grid rather than every pixel: 40_000 points out
#: of a million and a half is plenty to tell a picture from an empty field,
#: and keeps the readback off the critical path of the export.
PROBE_GRID = 200

#: The document `/probe` answers with: somewhere for the canvas readback to
#: run that shares an origin with the images it reads.
PROBE_PAGE = b"<!doctype html><meta charset=utf-8><title>probe</title>"


#: The images this script writes, offered back under a prefix of their own and
#: keyed by the file's own name rather than by where in the repository it is
#: written. They are named, not looked up: the request supplies a name to
#: compare against this mapping and never a path to walk.
EXPORTS = {
    Path(written).name: ROOT / written
    for written in (
        *(name for _s, name, _w, _h in SHOTS),
        *(name for _u, name, _r, _w, _h in PAGES),
        CI_RUN_IMAGE,
    )
}
EXPORT_PREFIX = "/exports/"


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the generated report, the exported images, and one blank page.

    A static handler rooted at the repository would put everything in the
    working tree — `.env` included — on a listening socket, and a rule that
    only inspected the request string would not stop it: the string
    `/site/report/../../.env` starts with the report's path and still names
    the repository root once it is decoded and normalised. So the root is the
    report directory itself, and every path this handler is willing to open is
    resolved first and then checked to be inside it. The images are not served
    from that tree at all; they are looked up by name under `/exports/`.

    `/probe` exists only to give the canvas readback a document of the same
    origin as the images.
    """

    def do_GET(self) -> None:  # noqa: N802 - the name is http.server's
        served = self._special()
        if served is None:
            super().do_GET()
            return
        status, content_type, body = served
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802 - the name is http.server's
        served = self._special()
        if served is None:
            super().do_HEAD()
            return
        status, content_type, body = served
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

    def _special(self) -> tuple[int, str, bytes] | None:
        """The two routes that are not files inside the report directory."""
        path = urllib.parse.unquote(self.path.split("?", 1)[0].split("#", 1)[0])
        if path == "/probe":
            return 200, "text/html; charset=utf-8", PROBE_PAGE
        if not path.startswith(EXPORT_PREFIX):
            return None
        name = path[len(EXPORT_PREFIX):]
        source = EXPORTS.get(name)
        if source is None or "/" in name:
            return 404, "text/plain; charset=utf-8", b"not exported by this script"
        return 200, "image/png", source.read_bytes()

    def send_head(self):  # returns what http.server returns: a file object, or None
        """Refuse anything that resolves outside the report directory.

        `SimpleHTTPRequestHandler.translate_path` decodes, normalises and
        joins against the root, so the decision here is made on the file that
        would actually be opened rather than on the string that asked for it.
        """
        candidate = Path(self.translate_path(self.path)).resolve()
        root = REPORT_DIR.resolve()
        if candidate != root and root not in candidate.parents:
            self.send_error(404, "not served by this exporter")
            return None
        return super().send_head()

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the per-request log; the export's own output is the story."""


@contextlib.contextmanager
def _serving() -> Iterator[str]:
    """The generated report over HTTP on loopback, for as long as the export runs."""
    handler = functools.partial(_Handler, directory=str(REPORT_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _collected_test_count(selection: tuple[str, ...]) -> int:
    """How many tests pytest collects for the selection the run was given.

    Runs in a subprocess with its own throwaway allure directory, so that
    collecting here cannot write into `allure-results` — the directory the
    report being photographed was just built from.
    """
    with tempfile.TemporaryDirectory() as spool:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", "--collect-only", "-q",
                "-p", "no:cacheprovider", f"--alluredir={spool}", *selection,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    ids = [line for line in proc.stdout.splitlines() if line.startswith("tests/") and "::" in line]
    if not ids:
        raise RuntimeError(
            f"pytest --collect-only {' '.join(selection)!s} collected nothing, so the "
            f"report cannot be checked against it.\n{proc.stdout}\n{proc.stderr}"
        )
    return len(ids)


def _summary_statistic(page: Page, summary_url: str) -> dict[str, int]:
    """The overview's own numbers, or an explanation of why there are none.

    A half-generated report is the ordinary failure here: the directory looks
    like a report, the page even renders, but `widgets/summary.json` is
    missing, truncated or is the server's 404 page. Left alone that surfaces
    as a JSON decode error naming nothing, so every case is turned into a
    sentence that says what was found at that URL and what to do about it.
    """
    fix = (
        "Generate the report again before taking this screenshot:\n"
        "  ~/.local/bin/allure generate allure-results --clean -o site/report"
    )
    response = page.request.get(summary_url)
    if not response.ok:
        raise RuntimeError(
            f"{summary_url} answered HTTP {response.status}, so the report being "
            f"photographed has no overview data. Either the report was never "
            f"generated into site/report, or it is not the report being served.\n{fix}"
        )
    body = response.text()
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{summary_url} is not JSON ({exc}); it starts with {body[:120]!r}. That "
            f"is what a half-written report, or a web server answering with an HTML "
            f"error page, looks like.\n{fix}"
        ) from exc
    statistic = parsed.get("statistic") if isinstance(parsed, dict) else None
    if not isinstance(statistic, dict):
        held = sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__
        raise RuntimeError(
            f"{summary_url} parsed, but it carries no 'statistic' object: it is "
            f"{len(body)} byte(s) holding {held}. A complete report always has "
            f"one.\n{fix}"
        )
    missing = sorted(
        key for key in ("total", "failed", "broken", "unknown")
        if not isinstance(statistic.get(key), int)
    )
    if missing:
        raise RuntimeError(
            f"{summary_url} reports a run without {', '.join(missing)}; its statistic "
            f"is {statistic}. The counts this screenshot is checked against cannot be "
            f"read from it.\n{fix}"
        )
    return statistic


def _require_report_is_complete_and_green(page: Page, base_url: str, ran: str) -> None:
    """Refuse to screenshot a report that is partial or has failures.

    Waiting for the text "test cases" only proves *an* overview rendered — a
    five-test partial with two failures says "test cases" too. The overview is
    drawn straight from this JSON, so reading it is reading what a viewer of
    the screenshot would actually see: how many cases the run reports, and
    whether any of them failed.

    This runs before the page is given time to render, and not after. The
    overview is drawn from `widgets/summary.json`: if that file is missing or
    malformed, the text worth waiting for is exactly the text that can never
    appear, and waiting for it first would replace every sentence below with a
    bare sixty-second timeout naming nothing. The file is read from the server
    rather than from the page, and the URL is built from the address being
    served rather than from `page.url`, which Allure rewrites with a fragment
    as it routes.

    `ran` is the marker expression the run was given, and is empty for the
    whole suite. A run that deliberately left part of the suite out passes the
    same expression to `--ran`, so a short report is still checked against a
    number rather than waved through.
    """
    summary_url = f"{base_url}/widgets/summary.json"
    stat = _summary_statistic(page, summary_url)
    not_green = stat["failed"] + stat["broken"] + stat["unknown"]
    expected = _collected_test_count(("-m", ran))
    asked_for = f'-m "{ran}"' if ran else "the whole suite"
    if not_green or stat["total"] != expected:
        raise RuntimeError(
            f"site/report/ is not a complete, passing run of {asked_for}: it reports "
            f"{stat['total']} test case(s) ({expected} expected from the current "
            f"suite), {stat['failed']} failed, {stat['broken']} broken, "
            f"{stat['unknown']} unknown. Regenerate it before taking this screenshot: "
            f"run the suite, then `~/.local/bin/allure generate allure-results "
            f"--clean -o site/report`. If the run left part of the suite out on "
            f"purpose, say so with --ran."
        )


def _png_size(path: Path) -> tuple[int, int]:
    """The dimensions the file itself carries, read out of its header.

    Asking the browser for a viewport is asking for one; the profile crops
    what it is given, so the number that matters is the one in the PNG.
    """
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise RuntimeError(f"{path.name} is not a PNG: it begins {header[:8]!r}.")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _ink(page: Page, image_url: str) -> tuple[int, float]:
    """How many colours a grid of samples finds, and how much is not the field.

    Read back through a canvas in the browser that produced the file: it is
    the only PNG decoder guaranteed to be present, and the image is fetched
    from the same origin as the page, which is what makes the readback legal.
    """
    result = page.evaluate(
        """async ([url, grid]) => {
          const img = new Image();
          img.src = url;
          await img.decode();
          const canvas = document.createElement('canvas');
          canvas.width = img.naturalWidth;
          canvas.height = img.naturalHeight;
          const ctx = canvas.getContext('2d', { willReadFrequently: true });
          ctx.drawImage(img, 0, 0);
          const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const seen = new Map();
          const stepX = Math.max(1, Math.floor(canvas.width / grid));
          const stepY = Math.max(1, Math.floor(canvas.height / grid));
          let sampled = 0;
          for (let y = 0; y < canvas.height; y += stepY) {
            for (let x = 0; x < canvas.width; x += stepX) {
              const i = (y * canvas.width + x) * 4;
              const key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
              seen.set(key, (seen.get(key) || 0) + 1);
              sampled += 1;
            }
          }
          let modal = 0;
          for (const count of seen.values()) modal = Math.max(modal, count);
          return { distinct: seen.size, ink: sampled ? (sampled - modal) / sampled : 0 };
        }""",
        [image_url, PROBE_GRID],
    )
    return int(result["distinct"]), float(result["ink"])


def _require_a_picture(page: Page, base_url: str, name: str, width: int, height: int) -> None:
    """Refuse to leave behind a file that is the right size and says nothing.

    A template whose stylesheet failed to apply, a report that rendered into
    an empty body, a screenshot taken before anything painted: each writes a
    perfectly valid PNG of the right dimensions. Measuring the file and then
    the pixels turns all three into a message instead of a commit.
    """
    path = ROOT / name
    offered = Path(name).name
    if EXPORTS.get(offered) != path:
        raise RuntimeError(
            f"{name} is not the file served back as {EXPORT_PREFIX}{offered}, so the "
            f"pixels measured below would belong to another picture. Two exports "
            f"whose paths end in the same file name cannot both be offered."
        )
    if not path.exists():
        raise RuntimeError(f"{name} was not written, though the screenshot reported no error.")
    actual = _png_size(path)
    if actual != (width, height):
        raise RuntimeError(
            f"{name} is {actual[0]}x{actual[1]}, not the {width}x{height} it has to be. "
            f"The profile crops anything else, so this file cannot be shipped."
        )
    distinct, ink = _ink(page, f"{base_url}{EXPORT_PREFIX}{offered}")
    if distinct < MIN_DISTINCT_COLOURS or ink < MIN_INK_SHARE:
        raise RuntimeError(
            f"{name} is {width}x{height} but essentially blank: a grid of samples found "
            f"{distinct} distinct colour(s) (at least {MIN_DISTINCT_COLOURS} expected) "
            f"and {ink:.3%} of them off the dominant one (at least {MIN_INK_SHARE:.0%} "
            f"expected). Something rendered an empty field — a stylesheet that did not "
            f"load, or a page photographed before it painted."
        )
    print(f"  {name}: {width}x{height}, {distinct} colours sampled, {ink:.1%} ink")


def _run_page(page: Page) -> dict:
    """What a workflow run page says about itself, as a visitor reads it.

    Three things, read in one pass so that all three describe the same moment:
    the value shown under "Status"; what every status icon the page actually
    draws says, taken from the icon's accessible name, which is what a screen
    reader would announce about the picture being taken; and where the run
    page's own content starts, which is where the crop starts. Icons that are
    in the markup but drawn nowhere — the page carries a second, hidden copy
    of its job list for narrow windows — are left out, because what is not on
    the screen is not in the photograph.
    """
    return page.evaluate(
        """() => {
          const label = Array.from(document.querySelectorAll('span, div, dt')).find(
            (e) => e.children.length === 0 && (e.textContent || '').trim() === 'Status');
          const status = label && label.nextElementSibling
            ? (label.nextElementSibling.textContent || '').trim()
            : null;
          const icons = Array.from(document.querySelectorAll('svg[aria-label]'))
            .map((svg) => ({
              name: svg.getAttribute('aria-label') || '',
              box: svg.getBoundingClientRect(),
            }))
            .filter((i) => i.name.includes(':') && i.box.width > 0 && i.box.height > 0)
            .map((i) => ({
              state: i.name.split(':')[0].trim().toLowerCase(),
              top: i.box.top + window.scrollY,
              bottom: i.box.bottom + window.scrollY,
            }));
          const main = document.querySelector('.application-main');
          return {
            status,
            icons,
            content_top: main ? main.getBoundingClientRect().top + window.scrollY : null,
          };
        }"""
    )


def _wait_for_the_run_to_be_drawn(page: Page, url: str) -> None:
    """Wait until the page has drawn a status and at least one job.

    The run page arrives as an application and fills itself in afterwards, so
    what exists a moment after load is a header with no run in it. Waiting for
    the two things this picture is about is waiting for the picture to exist —
    and when it never appears, saying what the page did show beats a selector
    timing out with nothing to say.
    """
    deadline = time.monotonic() + CI_RUN_TIMEOUT_SECONDS
    while True:
        found = _run_page(page)
        if found["status"] and found["icons"]:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"{url} never drew a run: after {CI_RUN_TIMEOUT_SECONDS}s it shows "
                f"{found['status'] or 'no status'} and {len(found['icons'])} job "
                f"icon(s). Either that URL is not a workflow run page, or the page "
                f"is no longer laid out the way this reader expects."
            )
        page.wait_for_timeout(500)


def _require_the_run_is_green(found: dict, url: str) -> None:
    """Refuse to photograph a run that is not passing.

    The same posture as the report check above, for the same reason: this
    picture is read as a claim that the pipeline passes, and the only honest
    place to get that claim is the page being photographed. Both halves are
    read — the status the run reports, and the state of every job drawn beside
    it — because a state this script has never seen is exactly the case where
    a green-looking picture would be worth checking by hand.
    """
    status = found["status"]
    if status != GREEN_RUN_STATUS:
        raise RuntimeError(
            f'{url} reports Status "{status}", not "{GREEN_RUN_STATUS}". A picture '
            f"of a run that failed, or of one still going, is the lie this script "
            f"exists to refuse. Pick a successful run of the workflow — the public "
            f"API lists them: /repos/<owner>/<repo>/actions/runs"
            f"?branch=main&status=success&per_page=1"
        )
    unknown = sorted({icon["state"] for icon in found["icons"]} - GREEN_JOB_STATES)
    if unknown:
        raise RuntimeError(
            f"{url} draws a job whose state this script does not photograph: "
            f"{', '.join(unknown)}. Expected one of {', '.join(sorted(GREEN_JOB_STATES))}. "
            f"If that state belongs in the picture, add it to GREEN_JOB_STATES; "
            f"otherwise the run is not the green one it looked like."
        )


def _frame(found: dict, url: str) -> dict[str, float]:
    """Where to cut the picture: the run page's content, at a fixed size."""
    top = found["content_top"]
    if top is None:
        raise RuntimeError(
            f"{url} holds no `.application-main`, so where the run page's own "
            f"content starts is unknown. A crop guessed at a fixed offset would "
            f"quietly photograph the wrong part of the page, so this is a refusal: "
            f"the page's layout has changed and the crop has to be re-read."
        )
    width, height = CI_RUN_SIZE
    return {"x": 0.0, "y": float(top), "width": float(width), "height": float(height)}


def _require_every_job_is_in_frame(found: dict, frame: dict[str, float], url: str) -> None:
    """Refuse a crop that cuts a job off the picture it is the point of."""
    bottom = frame["y"] + frame["height"]
    outside = [i for i in found["icons"] if i["top"] < frame["y"] or i["bottom"] > bottom]
    if outside:
        lowest = max(icon["bottom"] for icon in found["icons"])
        width, height = CI_RUN_SIZE
        raise RuntimeError(
            f"{len(outside)} of the {len(found['icons'])} job icon(s) on {url} fall "
            f"outside the {width}x{height} frame this script cuts: the lowest sits "
            f"at y={lowest:.0f} and the frame ends at y={bottom:.0f}. The job list is "
            f"what this picture is for, so raise CI_RUN_SIZE until all of it is "
            f"inside — and re-pin the new size where the image is checked."
        )


def _photograph_the_pipeline(browser, probe: Page, base_url: str, url: str) -> None:
    """One public run page, checked for what it claims and then cut to it."""
    width, height = CI_RUN_VIEWPORT
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=CI_RUN_TIMEOUT_SECONDS * 1000)
        _wait_for_the_run_to_be_drawn(page, url)
        # The graph draws its nodes and then lays them out. The rectangles the
        # frame is checked against are the ones the screenshot will hold only
        # once that has settled, so the reading that matters is taken after.
        page.wait_for_timeout(2000)
        found = _run_page(page)
        _require_the_run_is_green(found, url)
        frame = _frame(found, url)
        _require_every_job_is_in_frame(found, frame, url)
        (ROOT / CI_RUN_IMAGE).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=ROOT / CI_RUN_IMAGE, clip=frame, animations="disabled")
    finally:
        page.close()
    _require_a_picture(probe, base_url, CI_RUN_IMAGE, *CI_RUN_SIZE)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ran",
        metavar="MARKEREXPR",
        default="",
        help=(
            "the -m expression the photographed run was given, when it was not the "
            'whole suite, e.g. --ran "not e2e". The report is checked against what '
            "pytest collects for it."
        ),
    )
    parser.add_argument(
        "--ci-run",
        metavar="URL",
        default="",
        help=(
            f"the public GitHub Actions run page to photograph into {CI_RUN_IMAGE}, "
            "e.g. https://github.com/<owner>/<repo>/actions/runs/<id>. It is opened "
            "logged out, the way a visitor opens it, and a run that is not green is "
            "refused."
        ),
    )
    parser.add_argument(
        "--only",
        metavar="PICTURE",
        action="append",
        choices=EVERY_PICTURE,
        help=(
            "take one picture instead of every one this script knows how to take: "
            + ", ".join(EVERY_PICTURE)
            + ". Repeat the option for more than one. The cover and the report are "
            "exported from what is on this machine and the pipeline from a page on "
            "the network, so this is how either is refreshed without the other."
        ),
    )
    args = parser.parse_args(argv)
    if args.only:
        args.asked = frozenset(args.only)
    else:
        args.asked = LOCAL_PICTURES | ({CI_RUN_SHOT} if args.ci_run else set())
    if CI_RUN_SHOT in args.asked and not args.ci_run:
        parser.error(
            f"--only {CI_RUN_SHOT} needs the run to photograph: pass --ci-run URL."
        )
    # An option that describes a picture nobody asked for is a request that
    # will not happen, and saying so beats exporting something else in silence.
    if args.ci_run and CI_RUN_SHOT not in args.asked:
        parser.error(f"--ci-run names a page that --only leaves untaken; add --only {CI_RUN_SHOT}.")
    if args.ran and REPORT_SHOT not in args.asked:
        parser.error("--ran describes the report screenshot, which --only leaves untaken.")
    return args


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if REPORT_SHOT in args.asked and not (REPORT_DIR / "index.html").exists():
        raise RuntimeError(
            f"{REPORT_DIR.relative_to(ROOT)}/index.html does not exist, so there is no "
            f"report to photograph. Generate one first:\n"
            f"  ~/.local/bin/allure generate allure-results --clean -o site/report\n"
            f"Or take another picture instead: --only {CI_RUN_SHOT} needs nothing local."
        )
    with _serving() as base_url, sync_playwright() as p:
        browser = p.chromium.launch()
        # Closed the way the server is closed: every refusal in this script
        # leaves by raising, and the one resource that was not unwound in a
        # `finally` was the browser.
        try:
            probe = browser.new_page()
            probe.goto(f"{base_url}/probe", wait_until="load")

            if COVER_SHOT in args.asked:
                for source, name, width, height in SHOTS:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.goto((ROOT / source).as_uri())
                    page.wait_for_timeout(300)
                    page.screenshot(path=ROOT / name)
                    page.close()
                    _require_a_picture(probe, base_url, name, width, height)

            if REPORT_SHOT in args.asked:
                for path, name, ready, width, height in PAGES:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.goto(f"{base_url}{path}", wait_until="load", timeout=60_000)
                    _require_report_is_complete_and_green(page, base_url, args.ran)
                    page.wait_for_selector(ready, timeout=60_000)
                    page.wait_for_timeout(3000)
                    page.screenshot(path=ROOT / name)
                    page.close()
                    _require_a_picture(probe, base_url, name, width, height)

            if CI_RUN_SHOT in args.asked:
                _photograph_the_pipeline(browser, probe, base_url, args.ci_run)

            probe.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
