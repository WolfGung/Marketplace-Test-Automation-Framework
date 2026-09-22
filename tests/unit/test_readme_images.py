"""The pictures the README shows are the pictures the exporter wrote.

The README is the first thing anyone reads here, and its evidence is images:
the published report, the pipeline's run page, the architecture figure. A
broken one is somebody's first impression of this project, and a photograph
that quietly changed shape lays the page out differently for everybody -- so
the files are pinned the way the counts beside them already are in
``test_showcase_figures.py``.

Four things are held, each for its own reason. Every picture the README shows
from this repository exists, because a renamed file is an alt text where a
picture should be. Every photograph is the size ``scripts/make-assets.py``
refuses to write anything else at, so the pin and the exporter cannot drift
apart -- the sizes are read out of that script rather than typed again here.
Each one stays small enough to arrive while a reader is still looking at the
page. And the run photograph links to a run of this repository's pipeline,
because a picture of a green run that points anywhere else is the one failure
that still looks right.
"""
from __future__ import annotations

import importlib.util
import re
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

#: One Markdown image, and the link around it when it has one. GitHub renders
#: the evidence images as `[![alt](picture)](where it came from)`, so the
#: closing `](...)` is read here as part of finding the picture rather than by
#: a second pass over the same line.
IMAGE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)(?:\]\((?P<target>[^)\s]+)\))?"
)

#: What a picture on the first screen may weigh. Well under a megabyte, because
#: three of them load before a reader has decided whether to keep reading; well
#: above what a cropped screenshot of a page of text comes to, so meeting it is
#: cropping or scaling the picture rather than compressing it into mush.
MAX_PICTURE_BYTES = 400 * 1024

#: Where the run photograph is allowed to point: a run of this repository's own
#: pipeline. Anything else is a green picture of somebody else's build.
RUN_URL = re.compile(
    r"^https://github\.com/WolfGung/Marketplace-Test-Automation-Framework"
    r"/actions/runs/\d+$"
)


def _exporter():
    """`scripts/make-assets.py`, imported for the sizes it enforces.

    The file is a script rather than a module of the package, and its name is
    not an identifier, so it is loaded by path. Importing it runs nothing: the
    work is behind ``if __name__ == "__main__"``.
    """
    spec = importlib.util.spec_from_file_location(
        "make_assets", ROOT / "scripts" / "make-assets.py"
    )
    assert spec and spec.loader, "scripts/make-assets.py could not be loaded by path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exported_sizes() -> dict[str, tuple[int, int]]:
    """Every image the exporter writes, with the size it insists on."""
    exporter = _exporter()
    return {
        **{name: (width, height) for _source, name, width, height in exporter.SHOTS},
        **{name: (width, height) for _url, name, _ready, width, height in exporter.PAGES},
        exporter.CI_RUN_IMAGE: tuple(exporter.CI_RUN_SIZE),
    }


def _shown() -> dict[str, str | None]:
    """Every picture the README shows from this repository, and where it links.

    Images served from elsewhere -- the badges at the top of the page -- are
    left out: this module is about the files this repository ships, and a
    badge is somebody else's to keep working.
    """
    found: dict[str, str | None] = {}
    for match in IMAGE.finditer(README.read_text(encoding="utf-8")):
        src = match["src"]
        if src.startswith(("http://", "https://")):
            continue
        found[src] = match["target"]
    return found


SHOWN = _shown()
EXPORTED = _exported_sizes()
PHOTOGRAPHS = sorted(name for name in SHOWN if name in EXPORTED)


def _png_size(path: Path) -> tuple[int, int]:
    """The dimensions the file itself carries, read out of its header."""
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", (
        f"{path.relative_to(ROOT)} is shown in the README as a photograph, but it "
        f"is not a PNG: it begins {header[:8]!r}."
    )
    return struct.unpack(">II", header[16:24])


def test_the_reader_finds_the_pictures_the_readme_shows() -> None:
    """Without this, a rewritten README would pass by showing nothing."""
    assert SHOWN, (
        "no picture in README.md is served from this repository, so every test "
        "below would pass over an empty set. Either the evidence images were "
        "dropped from the page, or it is now written in a way this reader no "
        "longer understands."
    )
    assert PHOTOGRAPHS, (
        f"none of the pictures the README shows ({', '.join(sorted(SHOWN))}) is one "
        f"scripts/make-assets.py writes ({', '.join(sorted(EXPORTED))}), so no "
        f"photograph on the page is pinned to the size it was exported at."
    )


@pytest.mark.parametrize("src", sorted(SHOWN), ids=lambda v: v)
def test_a_picture_the_readme_shows_is_in_the_repository(src: str) -> None:
    """An alt text where a picture should be is what a missing file looks like."""
    assert (ROOT / src).exists(), (
        f"README.md shows {src}, which is not in the repository. A picture moved "
        f"or renamed is a broken image on the first screen a client reads; the "
        f"photographs are written by scripts/make-assets.py, which is also where "
        f"their paths are set."
    )


@pytest.mark.parametrize("src", PHOTOGRAPHS, ids=lambda v: v)
def test_a_photograph_is_the_size_its_exporter_writes(src: str) -> None:
    """The file on disk is the one the exporter measured, not a stand-in."""
    expected = EXPORTED[src]
    assert _png_size(ROOT / src) == expected, (
        f"{src} is {'x'.join(map(str, _png_size(ROOT / src)))}, but "
        f"scripts/make-assets.py writes it at {'x'.join(map(str, expected))} and "
        f"refuses any other size. Either it was replaced by hand, or the exporter "
        f"was re-aimed and this picture was never taken again."
    )


@pytest.mark.parametrize("src", sorted(SHOWN), ids=lambda v: v)
def test_a_picture_on_the_first_screen_is_small_enough_to_arrive(src: str) -> None:
    """Evidence nobody waits for is evidence nobody sees."""
    size = (ROOT / src).stat().st_size
    assert size <= MAX_PICTURE_BYTES, (
        f"{src} is {size / 1024:.0f} KB, over the {MAX_PICTURE_BYTES // 1024} KB a "
        f"picture on this page may weigh. Crop it or take it in a smaller window -- "
        f"the sizes are in scripts/make-assets.py -- rather than compressing it "
        f"until the text in it cannot be read."
    )


def test_the_run_photograph_links_to_a_run_of_this_pipeline() -> None:
    """A picture of a green run is a claim about *this* project's pipeline.

    The exporter refuses to photograph a run that is not green, which settles
    what the picture shows. Where it points is settled here: a link to another
    repository's run, or to the workflow's list of runs rather than to the one
    in the picture, would be the same picture making a claim nobody can check.
    """
    ci_run = _exporter().CI_RUN_IMAGE
    assert ci_run in SHOWN, (
        f"README.md no longer shows {ci_run}, the photograph of the pipeline. "
        f"Either the evidence section lost it, or it is shown under another path "
        f"than the one the exporter writes."
    )
    target = SHOWN[ci_run]
    assert target and RUN_URL.match(target), (
        f"README.md shows {ci_run} linking to {target!r}, which is not a run of "
        f"this repository's pipeline. The picture shows one run, and the link has "
        f"to be that run: https://github.com/WolfGung/"
        f"Marketplace-Test-Automation-Framework/actions/runs/<id>"
    )
