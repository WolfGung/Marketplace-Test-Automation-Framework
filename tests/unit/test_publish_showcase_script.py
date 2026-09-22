"""The publish script must not keep its own copy of the video selection rule.

`showcase.build.PREFERRED_RECORDINGS` (used by `_pick_video`) is the one
place that decides which recording is the purchase and gets a `<video>`
block on the page. A second, independent list of glob patterns in the shell
script -- copying a file `build.py` would not caption -- is exactly how a
real recording ended up published to `gh-pages` while the page never
referenced it (found in review). These tests do not re-implement the
selection rule; they make sure there is nowhere else for a second one to
live, and that the script hands the builder the real videos directory
instead of relying on a default that only happens to be right sometimes.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "publish-showcase.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_script_has_no_hardcoded_video_glob() -> None:
    text = _text()
    assert "*.webm" not in text, (
        "a webm glob literal in the script is a second, independent video "
        "selection rule that showcase/build.py's PREFERRED_RECORDINGS cannot "
        "be kept in step with"
    )
    assert "test_logged_in_user_can_place_an_order" not in text
    assert "test_product_details_match_api_catalog" not in text


def test_the_script_does_not_copy_a_video_itself() -> None:
    """Only `showcase/build.py` may write `site/media/checkout.webm` -- a
    second `cp` to that path from the script would be exactly the
    conflicting write the divergence bug came from. (The path is named in
    this script's own comments explaining why not; only a command line
    actually writing there is disallowed.)"""
    commands = [
        line.strip() for line in _text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any("media/checkout.webm" in line for line in commands)


def test_the_script_gives_the_builder_the_real_videos_directory() -> None:
    """`showcase/build.py --videos` must see this run's actual videos
    directory, not its own default, or its own placement (the only one that
    exists once the script stops duplicating it) would be wrong too."""
    text = _text()
    assert "showcase/build.py" in text
    assert '--videos "$VIDEOS"' in text


def test_the_script_has_no_hardcoded_trace_glob() -> None:
    """The trace is picked by `showcase.build.PREFERRED_TRACES` for exactly the
    reason the recording is, so the script must not learn to pick one too."""
    assert "*.zip" not in _text()


def test_the_script_gives_the_builder_the_real_traces_directory() -> None:
    assert '--traces "$TRACES"' in _text()


def test_the_script_refuses_to_push_outside_ci_by_default() -> None:
    """A local run must not be able to repeat the accident that seeded
    `gh-pages` with a synthetic publication: the push is gated on either
    running under GitHub Actions or an explicit opt-in, not unconditional."""
    text = _text()
    assert "GITHUB_ACTIONS" in text
    assert "PUBLISH_SHOWCASE" in text


def test_the_script_supports_starting_the_trend_over() -> None:
    """A documented, off-by-default escape hatch for discarding accumulated
    history, meant to be used for exactly one publication."""
    assert "RESET_SHOWCASE_HISTORY" in _text()


def test_the_script_merges_the_two_jobs_results_through_the_tested_module() -> None:
    """`showcase/merge.py` is what `tests/unit/test_showcase_merge.py`
    actually exercises; the script has to be the one calling it, or that
    coverage says nothing about what ships."""
    text = _text()
    assert "showcase/merge.py categories" in text
    assert "showcase/merge.py environment" in text
