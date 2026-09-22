"""Build the showcase page from the artefacts of a single run.

Every number on the page comes from the Allure results of the run being
published. Nothing here is written by hand, because a page that disagrees with
its own report is worse than no page.

Two artefacts are optional: the checkout recording and the two diagrams. They
are produced by other steps and may simply not be there. When one is missing
the page says so in words, rather than offering a broken image or a black
video frame -- a showcase that shows a broken box has already lost the reader.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlparse

#: The three layers a product test can prove its claim at. A case belongs to
#: exactly one of them, and the page's split by layer is counted from these.
LAYERS = ("api", "ui", "e2e")

#: The suite's other markers. They say what a case is *about* — a negative or
#: boundary case, a check that spans the API and the browser, the smoke set —
#: and a case carries them on top of its layer, never instead of one. Treating
#: any of them as a fourth layer would double-count every case that carries one
#: and would put layers on the page that the suite does not have.
CROSS_CUTTING = ("smoke", "negative", "integration")

if set(LAYERS) & set(CROSS_CUTTING):  # pragma: no cover - guards a typo above
    raise RuntimeError("a marker cannot be both a layer and a cross-cutting tag")

#: A recording smaller than this is a truncated file, not a video. The publish
#: step applies the same floor with `find -size +10240c`, which is this number
#: written the way find counts: both admit a file of more than 10 KiB.
MIN_VIDEO_BYTES = 10 * 1024

#: The recording the page publishes, by name. A run records every case marked
#: `e2e` and leaves the files as `checkout-<test name>.webm`, so more than one
#: is normal: the second end-to-end case opens a product page to compare it
#: with the API and never buys anything. Both are far above the floor above, so
#: size cannot tell them apart, and a page that captioned the cross-layer check
#: as the purchase would misdescribe what the reader is watching. The publish
#: step picks by the same name.
PREFERRED_RECORDINGS = ("*test_logged_in_user_can_place_an_order*.webm",)

ASSETS_DIR = Path(__file__).parent / "assets"


@dataclass
class Tally:
    """What happened to one group of results."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    unknown: int = 0
    smoke: int = 0
    flaky: int = 0

    @property
    def not_passed(self) -> int:
        """Everything that did not come back green, however it got there."""
        return self.total - self.passed

    def record(self, status: str, smoke: bool, flaky: bool, where: str) -> None:
        self.total += 1
        if smoke:
            self.smoke += 1
        if flaky:
            self.flaky += 1
        if status == "passed":
            self.passed += 1
        elif status in {"failed", "broken"}:
            self.failed += 1
        elif status == "skipped":
            self.skipped += 1
        elif status == "unknown":
            self.unknown += 1
        else:
            # Every counted result has to land in a bucket the page can show.
            # Silently dropping one produces a page whose own totals do not add
            # up, which is the single thing this page cannot afford.
            raise ValueError(f"unrecognised Allure status {status!r} in {where}")


@dataclass
class RunSummary:
    """One run, split by what each result is actually evidence of.

    The application and the suite's own tooling are counted apart, because the
    page leads with the first. A reader looking at a project about testing a
    marketplace reads the big number as coverage of that marketplace, and tests
    of this builder would inflate it on work that is not product coverage at
    all.
    """

    product: Tally = field(default_factory=Tally)
    framework: Tally = field(default_factory=Tally)
    by_layer: dict[str, int] = field(default_factory=dict)
    finished: datetime = datetime.fromtimestamp(0, tz=UTC)

    # The whole run, for anything that needs it. Derived, so the parts and the
    # whole cannot drift apart.
    @property
    def total(self) -> int:
        return self.product.total + self.framework.total

    @property
    def passed(self) -> int:
        return self.product.passed + self.framework.passed

    @property
    def failed(self) -> int:
        return self.product.failed + self.framework.failed

    @property
    def skipped(self) -> int:
        return self.product.skipped + self.framework.skipped

    @property
    def unknown(self) -> int:
        return self.product.unknown + self.framework.unknown

    @property
    def smoke(self) -> int:
        return self.product.smoke + self.framework.smoke

    @property
    def flaky(self) -> int:
        return self.product.flaky + self.framework.flaky


def _identity(body: dict, path: Path) -> str:
    """What makes two result files two attempts at the same test.

    ``historyId`` is Allure's own answer and is what its report groups on, so
    it is used whenever the file carries one. A result written by something
    that does not set it still has to be grouped, so the fallback is the pair
    the history id is derived from anyway: the fully qualified name and the
    parameters of the case. The file name is the last resort, which makes an
    unidentifiable result its own test and keeps it counted.
    """
    history = body.get("historyId")
    if history:
        return f"history:{history}"
    parameters = sorted(
        (str(p.get("name")), str(p.get("value")))
        for p in body.get("parameters", [])
        if isinstance(p, dict)
    )
    name = body.get("fullName") or body.get("name")
    if not name:
        return f"file:{path.name}"
    return f"name:{name}:{parameters}"


def _published_attempt(attempts: list[tuple[Path, dict]]) -> tuple[Path, dict]:
    """The attempt Allure shows for a test, out of all the attempts it made.

    A rerun writes a second result file for the same test, and the report
    counts the last attempt while keeping the earlier ones as retries. The
    page has to agree with the report it sits beside, so it reads the same
    attempt: the newest by the times the run recorded, with the file name
    breaking a tie so the choice is stable across machines.
    """
    return max(
        attempts,
        key=lambda item: (
            int(item[1].get("stop") or 0),
            int(item[1].get("start") or 0),
            item[0].name,
        ),
    )


def summarise(results_dir: Path) -> RunSummary:
    """Count one run, with each test counted once however often it ran.

    Allure writes one result file per *attempt*, so counting files would report
    three tests where two ran and would put a failure on the page beside a
    report that shows none. This suite does not rerun a failed test today, but
    the results it publishes are merged from two CI jobs and a re-run job would
    contribute a second attempt for the same case, so the grouping is not
    optional: the files are grouped into tests first, and every figure the page
    states — the totals, the smoke set, the layer split — is counted from the
    grouped tests. A test that needed a second attempt to pass is counted as
    the pass it ended on and named separately as a flake, because the run that
    hides its retries is the one nobody can trust.
    """
    files = sorted(Path(results_dir).glob("*-result.json"))
    if not files:
        raise ValueError(f"no Allure results in {results_dir}")

    attempts: dict[str, list[tuple[Path, dict]]] = {}
    stops: list[int] = []
    for path in files:
        body = json.loads(path.read_text(encoding="utf-8"))
        attempts.setdefault(_identity(body, path), []).append((path, body))
        if body.get("stop"):
            stops.append(int(body["stop"]))

    summary = RunSummary(by_layer={layer: 0 for layer in LAYERS})
    for tries in attempts.values():
        path, body = _published_attempt(tries)
        status = body.get("status", "unknown")
        flaky = status == "passed" and any(
            other.get("status") != "passed" for _, other in tries if other is not body
        )
        tags = {
            item["value"] for item in body.get("labels", []) if item.get("name") == "tag"
        }

        layers = [layer for layer in LAYERS if layer in tags]
        if len(layers) > 1:
            # A case proves its thing at one layer; two markers means the
            # selection rules in pytest.ini no longer mean what the page says
            # they mean. Counting it once under whichever tag sorts first would
            # hide that, and the layer totals would quietly stop adding up.
            raise ValueError(
                f"{body.get('name', path.name)} carries more than one layer "
                f"tag ({', '.join(layers)}); a case belongs to one layer"
            )
        if not layers:
            # A case that lives under tests/api, tests/ui or tests/e2e is a
            # claim about the product; missing its layer tag is a mistake in
            # the test, not a sign that it belongs with the framework's own
            # checks. Left alone it would vanish from the product totals above
            # and pad the framework count instead, with nothing failing.
            qualifier = (body.get("fullName") or body.get("name") or path.name).split("#", 1)[0]
            stray = next(
                (
                    layer for layer in LAYERS
                    if qualifier == f"tests.{layer}" or qualifier.startswith(f"tests.{layer}.")
                ),
                None,
            )
            if stray is not None:
                raise ValueError(
                    f"{body.get('name', path.name)} sits under tests/{stray} "
                    f"({qualifier}) but carries no layer tag; add the marker "
                    f"for the layer it proves, or it silently drops out of the "
                    f"product totals and inflates the framework count instead"
                )
        for layer in layers:
            summary.by_layer[layer] += 1

        group = summary.product if layers else summary.framework
        group.record(status, "smoke" in tags, flaky, where=path.name)

    if stops:
        summary.finished = datetime.fromtimestamp(max(stops) / 1000, tz=UTC)
    return summary


def _text(value: object) -> str:
    """Escape a value for text or for an attribute's contents."""
    return html.escape(str(value), quote=True)


def _safe_url(url: str) -> str:
    """An escaped http(s) or relative URL; empty for anything else.

    The run URL arrives from the environment, and the page puts it in an
    ``href``. Escaping alone would still let ``javascript:`` through, so the
    scheme is checked as well and an unusable value is treated as no value:
    the block that links the run is dropped rather than rendered broken.
    """
    candidate = url.strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if candidate.startswith("//"):  # protocol-relative: not ours to resolve
        return ""
    return html.escape(candidate, quote=True)


def _pick_video(video_dir: Path) -> Path | None:
    """The recording to publish -- the *only* place this choice is made.

    Only a name in ``PREFERRED_RECORDINGS`` is the purchase; anything else in
    the directory is a recording of some other case and must not be captioned
    as if it were the order being placed. A run that leaves no preferred file
    gets no video at all. ``scripts/publish-showcase.sh`` used to keep its own,
    separate copy of this rule as a second glob-matching loop, and the two
    went out of step: the script would publish the cross-layer recording as a
    fallback while this function still decided the page should show none,
    shipping a real file to ``gh-pages`` that nothing on the page ever
    referenced. The script now calls ``build_site`` with the real videos
    directory and does no selection of its own; this function is where a
    fallback would need to be added if one is ever wanted, precisely so that
    the page and the file it ships together can never disagree again.
    """
    usable = sorted(
        p for p in Path(video_dir).glob("*.webm")
        if p.is_file() and p.stat().st_size > MIN_VIDEO_BYTES
    )
    for pattern in PREFERRED_RECORDINGS:
        for candidate in usable:
            if fnmatch(candidate.name, pattern):
                return candidate
    return None


def _place(source: Path | None, target: Path) -> bool:
    """Put an optional artefact beside the page. True when the page can use it.

    A file already sitting at the target counts: the publish step may have put
    it there before calling this module.
    """
    if target.is_file() and target.stat().st_size > 0:
        return True
    if source is None or not Path(source).is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def _resolve(page: str, name: str, keep: bool) -> str:
    """Keep or drop one conditional block of the template.

    Blocks are written as ``<!--[if name]-->...<!--[else name]-->...<!--[end
    name]-->``; the ``else`` half is optional.
    """
    pattern = re.compile(
        rf"<!--\[if {name}\]-->(?P<then>.*?)"
        rf"(?:<!--\[else {name}\]-->(?P<otherwise>.*?))?"
        rf"<!--\[end {name}\]-->",
        re.DOTALL,
    )

    def _swap(match: re.Match[str]) -> str:
        chosen = match.group("then") if keep else (match.group("otherwise") or "")
        return chosen.strip("\n")

    return pattern.sub(_swap, page)


def build_site(
    results_dir: Path,
    out_dir: Path,
    revision: str,
    run_url: str,
    video_dir: Path = Path("videos"),
    assets_dir: Path = ASSETS_DIR,
) -> None:
    summary = summarise(results_dir)
    safe_run_url = _safe_url(run_url)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    present = {
        "video": _place(_pick_video(video_dir), out_dir / "media" / "checkout.webm"),
        "architecture": _place(
            Path(assets_dir) / "architecture.svg", out_dir / "assets" / "architecture.svg"
        ),
        "pipeline": _place(
            Path(assets_dir) / "ci-pipeline.svg", out_dir / "assets" / "ci-pipeline.svg"
        ),
        "run": bool(safe_run_url),
        # The page describes the two end-to-end cases in words, and those words
        # are false in front of a zero. A run without them is not what gets
        # published -- the publish job needs the browser leg, which is where
        # they live -- but "0 end-to-end: one that places an order and one
        # that..." is exactly the self-contradiction this page exists to avoid,
        # so the prose is dropped rather than left standing over the figure.
        "e2e": summary.by_layer.get("e2e", 0) > 0,
        "product_skipped": summary.product.skipped > 0,
        "product_unknown": summary.product.unknown > 0,
        "product_flaky": summary.product.flaky > 0,
        "framework": summary.framework.total > 0,
        "framework_clean": summary.framework.not_passed == 0,
        "framework_flaky": summary.framework.flaky > 0,
    }

    page = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    for name, keep in present.items():
        page = _resolve(page, name, keep)
    page = _resolve(page, "diagrams", present["architecture"] or present["pipeline"])

    # The figures the page leads with are the product suite's; the framework's
    # are named separately, below them, in the template.
    # Everything below is escaped on its way into the page. The counts cannot
    # carry markup and the revision comes from git, but a build tool for a
    # client-facing page should not hold a working injection primitive at all.
    # ``_safe_url`` has already escaped the run URL for its attribute.
    for key, value in {
        "{{TOTAL}}": _text(summary.product.total),
        "{{PASSED}}": _text(summary.product.passed),
        "{{FAILED}}": _text(summary.product.failed),
        "{{SKIPPED}}": _text(summary.product.skipped),
        "{{UNKNOWN}}": _text(summary.product.unknown),
        "{{SMOKE}}": _text(summary.product.smoke),
        "{{FLAKY}}": _text(summary.product.flaky),
        "{{API}}": _text(summary.by_layer.get("api", 0)),
        "{{UI}}": _text(summary.by_layer.get("ui", 0)),
        "{{E2E}}": _text(summary.by_layer.get("e2e", 0)),
        "{{FRAMEWORK}}": _text(summary.framework.total),
        "{{FRAMEWORK_OPEN}}": _text(summary.framework.not_passed),
        "{{FRAMEWORK_FLAKY}}": _text(summary.framework.flaky),
        "{{RUN_TOTAL}}": _text(summary.total),
        "{{FINISHED}}": _text(summary.finished.strftime("%d %B %Y, %H:%M UTC")),
        "{{REVISION}}": _text(revision[:7]),
        "{{RUN_URL}}": safe_run_url,
    }.items():
        page = page.replace(key, value)

    (out_dir / "index.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("allure-results"))
    parser.add_argument("--out", type=Path, default=Path("site"))
    parser.add_argument("--revision", default="local")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--videos", type=Path, default=Path("videos"))
    parser.add_argument("--assets", type=Path, default=ASSETS_DIR)
    args = parser.parse_args()
    build_site(
        args.results, args.out, args.revision, args.run_url,
        video_dir=args.videos, assets_dir=args.assets,
    )
