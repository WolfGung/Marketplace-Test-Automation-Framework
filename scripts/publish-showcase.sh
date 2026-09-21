#!/usr/bin/env bash
# scripts/publish-showcase.sh — assemble the site and push it to gh-pages.
#
# History is carried over from the previous publication: without it the report
# shows a single run and no trend.
set -euo pipefail

RESULTS="${1:-allure-results}"
VIDEOS="${2:-videos}"
SITE="site"
ALLURE_VERSION="2.30.0"

# A prior run that died mid-way (a killed job, a crashed shell) can leave a
# worktree registered without a directory, or a directory without the
# registration; either half-state must not stop this run from starting clean.
# A prior *successful* local run leaves something too: `git checkout
# --orphan gh-pages-new` creates a local branch that removing the worktree
# does not delete, so a second local run collides on the branch name with
# "fatal: a branch named 'gh-pages-new' already exists" — found by actually
# running this script twice in a row while verifying the history fix below,
# not by inspection.
rm -rf "$SITE" published publish-tree
git worktree prune
# A leftover gh-pages-new is only ever ours to delete when its tip commit is
# one we made: same bot identity, same "Publish showcase for ..." subject
# (both hard-coded a few lines below, at the `git commit` this branch comes
# from). Anything else with that name — someone's own work-in-progress branch
# — is not this script's to destroy; stop and say so instead.
if git show-ref --verify --quiet refs/heads/gh-pages-new; then
  branch_author="$(git log -1 --format='%ae' gh-pages-new)"
  branch_subject="$(git log -1 --format='%s' gh-pages-new)"
  if [ "$branch_author" = "41898282+github-actions[bot]@users.noreply.github.com" ] \
     && [[ "$branch_subject" == "Publish showcase for "* ]]; then
    git branch -D gh-pages-new
  else
    echo "publish: a local branch 'gh-pages-new' already exists and its last" >&2
    echo "commit is not this script's own (author: ${branch_author:-none}," >&2
    echo "subject: ${branch_subject:-none}). Refusing to delete it — move it" >&2
    echo "out of the way or remove it yourself, then rerun this script." >&2
    exit 1
  fi
fi
# Fetching the previous publication is allowed to fail quietly: the very
# first publication has no gh-pages history yet, and that must degrade to a
# report with no trend, not to a broken run. Copying it once we already have
# it in hand is a different posture: at that point the source is right there
# in the worktree, so a failure means something is actually wrong (a
# permissions problem, a corrupted history directory) and the run should
# stop rather than silently publish a trendless report while claiming
# otherwise.
git fetch origin gh-pages --depth 1 || true
if git rev-parse --verify origin/gh-pages >/dev/null 2>&1; then
  git worktree add published origin/gh-pages
  if [ -d published/report/history ]; then
    # `cp -r src dst` copies INTO dst when dst already exists, nesting the
    # history at history/history/*.json instead of replacing it — Allure
    # then sees no history at the path it expects, and the report loses its
    # trend even though this step reported success. `$RESULTS/history`
    # already exists whenever a person reruns this script locally against a
    # results directory left over from a previous run (exactly what the
    # brief's own Step 4 asks for), so the destination is cleared first to
    # make the copy a replace, not a merge.
    rm -rf "$RESULTS/history"
    cp -r published/report/history "$RESULTS/history"
    echo "publish: carried over Allure history from the previous publication"
  fi
fi

npx -y "allure-commandline@$ALLURE_VERSION" generate "$RESULTS" --clean -o "$SITE/report"

# `showcase/` is not part of the `ecom-marketplace-taf` package that `pip
# install .` puts on site-packages — setuptools is configured to find
# packages under `src` only (pyproject.toml, [tool.setuptools.packages.find]
# where = ["src"]) — so the builder is only importable with the repository
# root on PYTHONPATH. This has no effect on a developer's own shell, where
# the checkout itself is usually already the working tree of an editable
# install or a path someone `cd`ed into by hand; a CI runner has neither, so
# leaving this out fails there and nowhere else.
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" python showcase/build.py \
  --results "$RESULTS" --out "$SITE" \
  --revision "${GITHUB_SHA:-local}" \
  --run-url "${RUN_URL:-}" \
  --videos "$VIDEOS"

mkdir -p "$SITE/assets" "$SITE/media"
cp showcase/assets/*.svg "$SITE/assets/"

# Two end-to-end cases can leave a recording in the same run: the logged-in
# checkout that carries the order through to confirmation, and the
# cross-layer check that only opens a product page to compare it against the
# API and never buys anything. The order test is the complete flow, so it is
# published when present; the API/UI comparison's recording is only a
# fallback. This is a deliberate choice by name, not a guess by file size —
# both recordings are well above the truncated-file floor, so size cannot
# tell them apart. `showcase/build.py` places a video by the same floor
# (`MIN_VIDEO_BYTES`) on its own, first, best-effort pass, and this copy —
# which runs after it and knows the real `$VIDEOS` argument — is what
# actually lands in the published site; `-size +10240c` is that floor written
# in the units find counts: bytes, not 1 KB blocks, so the two are the same
# 10 KiB rather than 10240 against 10000.
video=""
for pattern in \
  '*test_logged_in_user_can_place_an_order*.webm' \
  '*test_product_details_match_api_catalog*.webm'
do
  candidate=$(find "$VIDEOS" -name "$pattern" -size +10240c 2>/dev/null | sort | head -1 || true)
  if [ -n "$candidate" ]; then
    video="$candidate"
    break
  fi
done
if [ -n "$video" ]; then
  echo "publish: using recording $video"
  cp "$video" "$SITE/media/checkout.webm"
else
  echo "publish: no recording found in $VIDEOS — the page will show no video" >&2
fi

rm -rf published
git worktree add --detach publish-tree
cd publish-tree
git checkout --orphan gh-pages-new
git rm -rf . >/dev/null 2>&1 || true
cp -r "../$SITE/." .
touch .nojekyll
git add -A
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -m "Publish showcase for ${GITHUB_SHA:-local}"
# Plain --force, not --force-with-lease, and on purpose. gh-pages is a
# publication, not a history: every single run is meant to replace it
# completely, including a rerun of the very same commit, so there is no
# "someone else's work I might clobber" case here for a lease to protect —
# that is what the workflow's `concurrency` group (see ci.yml) is for, by
# making sure only one publish is ever running at a time. A lease would also
# tie this push's success to the early, best-effort `git fetch origin
# gh-pages` above, which is deliberately allowed to fail quietly (a first
# publication has no previous gh-pages to fetch). A bare `--force-with-lease`
# uses that same fetch as its expected value, so a transient network blip on
# the read side — something this script already shrugs off — would turn into
# a hard failure on the write side instead: a legitimate publication rejected
# for a reason that has nothing to do with a race. That trade is worse than
# the race it would guard against once concurrency already serialises
# publications.
git push --force origin gh-pages-new:gh-pages
cd ..
git worktree remove --force publish-tree
