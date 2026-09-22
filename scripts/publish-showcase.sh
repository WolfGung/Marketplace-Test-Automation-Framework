#!/usr/bin/env bash
# scripts/publish-showcase.sh — assemble the site and push it to gh-pages.
#
# History is carried over from the previous publication: without it the report
# shows a single run and no trend.
set -euo pipefail

API_RESULTS="${1:-allure-results-api}"
UI_RESULTS="${2:-allure-results-ui}"
VIDEOS="${3:-videos}"
RESULTS="allure-results"
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
rm -rf "$RESULTS" "$SITE" published publish-tree
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

# Two CI jobs, two raw results directories: the per-test result/container/
# attachment files are named by a random UUID per run, so copying both sets
# straight into one directory cannot collide. `categories.json` and
# `environment.properties` are the two fixed-name exceptions — the first is
# identical by construction, the second genuinely differs between an
# API-only job and a browser job — and `showcase/merge.py` is what decides
# what "merged" means for those two, rather than letting whichever job's
# artefact this script copies last win by accident (the way a naive `cp -r`
# of both into the same path, or an artefact download to a shared path,
# would). See `showcase/merge.py` and `tests/unit/test_showcase_merge.py`.
mkdir -p "$RESULTS"
for dir in "$API_RESULTS" "$UI_RESULTS"; do
  if [ -d "$dir" ]; then
    find "$dir" -mindepth 1 -maxdepth 1 \
      ! -name categories.json ! -name environment.properties \
      -exec cp -t "$RESULTS" {} +
  fi
done
python3 showcase/merge.py categories \
  "$API_RESULTS/categories.json" "$UI_RESULTS/categories.json" \
  --out "$RESULTS/categories.json"
python3 showcase/merge.py environment \
  "$API_RESULTS/environment.properties" "$UI_RESULTS/environment.properties" \
  --out "$RESULTS/environment.properties"

# `RESET_SHOWCASE_HISTORY` is a documented, off-by-default escape hatch: set
# it and the trend starts over from this publication instead of carrying the
# previous one forward. It exists for exactly one situation — the published
# history needs to be discarded on purpose (contaminated by a run that was
# never a real CI publication, say) — and it is meant to be set for exactly
# one run and then unset again, both as deliberate, explained commits; it is
# not a normal knob left on. With it set, the fetch below is skipped entirely
# so a stale $RESULTS/history from a previous local run in this same
# directory cannot leak into a "fresh" history either.
if [ -n "${RESET_SHOWCASE_HISTORY:-}" ]; then
  echo "publish: RESET_SHOWCASE_HISTORY is set — starting the Allure trend over from this run" >&2
else
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
      # results directory left over from a previous run, so the destination is
      # cleared first to make the copy a replace, not a merge.
      rm -rf "$RESULTS/history"
      cp -r published/report/history "$RESULTS/history"
      echo "publish: carried over Allure history from the previous publication"
    fi
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
#
# `--videos "$VIDEOS"` is passed explicitly, and on purpose: `build_site`
# picks the recording and writes it to `$SITE/media/checkout.webm` itself
# (`showcase/build.py`'s own `_pick_video`/`_place`), and that is now the
# *only* place a video is ever selected or copied — a second, independent
# selection used to live in this script too, matching by a hardcoded glob
# list that could and did go out of step with `PREFERRED_RECORDINGS`: a real
# recording shipped to `gh-pages` while the page never referenced it. One
# list now, in `showcase/build.py`; `tests/unit/test_publish_showcase_script.py`
# fails if a second one comes back here.
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" python showcase/build.py \
  --results "$RESULTS" --out "$SITE" \
  --revision "${GITHUB_SHA:-local}" \
  --run-url "${RUN_URL:-}" \
  --videos "$VIDEOS"

mkdir -p "$SITE/assets" "$SITE/media"
cp showcase/assets/*.svg "$SITE/assets/"

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

# The push is opt-in by construction, not unconditional: a local run without
# this gate is exactly what turned a "dry run" into a real publication of
# synthetic data (a stale local results directory, a fabricated video) on the
# public gh-pages branch, once it turned out this machine already had working
# push credentials — the assumption that a missing credential would make the
# push a no-op does not hold everywhere. `GITHUB_ACTIONS` is set to `true` by
# GitHub Actions on every job, unprompted, so a genuine CI publication needs
# no extra configuration; `PUBLISH_SHOWCASE` is the explicit, named way for a
# person to opt in locally when they mean to actually publish. Anything else
# prints what would have been pushed and stops — assembly still succeeded, so
# this is not a failure, and the result can be inspected in `$SITE` or in the
# diff below without anything having left this machine.
if [ "${GITHUB_ACTIONS:-}" = "true" ] || [ -n "${PUBLISH_SHOWCASE:-}" ]; then
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
else
  echo "publish: not a CI run (GITHUB_ACTIONS is not 'true') and PUBLISH_SHOWCASE is" >&2
  echo "publish: not set — declining to push. The assembled site is in $SITE/ for" >&2
  echo "publish: inspection. This is what would have been published:" >&2
  if git rev-parse --verify origin/gh-pages >/dev/null 2>&1; then
    git --no-pager diff --stat origin/gh-pages HEAD >&2
  else
    git --no-pager show --stat HEAD >&2
  fi
  echo "publish: set PUBLISH_SHOWCASE=1 to push anyway." >&2
fi
cd ..
git worktree remove --force publish-tree
