#!/usr/bin/env bash
# scripts/build-showcase.sh — assemble the showcase site in site/, and stop there.
#
#   bash scripts/build-showcase.sh [api-results] [ui-results] [videos] [traces]
#
# site/ gets the Allure report of both test jobs, the page showcase/build.py
# writes from the same results, the two diagrams, and the recording and the
# Playwright trace of the purchase when the run left them. The report's trend
# comes from the previous publication: its Allure history is read back from the
# published site (SITE_URL) before the report is generated. A first publication
# has none and an unreachable site gives none; either way the report shows this
# run with no trend, and the build goes on.
#
# Nothing is published from here. The CI run uploads site/ as a GitHub Pages
# artifact and deploys it (the `showcase` job in .github/workflows/ci.yml), so
# this script writes no branch, makes no commit and pushes nothing. Run locally,
# it leaves the assembled site in site/ and nothing else.
#
#   SITE_URL    the published site (default: this repository's Pages address)
#   ALLURE_BIN  an allure executable to run instead of the pinned
#               allure-commandline, which is otherwise fetched through npx
set -euo pipefail

API_RESULTS="${1:-allure-results-api}"
UI_RESULTS="${2:-allure-results-ui}"
VIDEOS="${3:-videos}"
TRACES="${4:-traces}"
RESULTS="allure-results"
SITE="site"
ALLURE_VERSION="2.30.0"
# Where the previous publication is served. CI sets it; the default is this
# repository's own GitHub Pages address. It names a directory, so it ends in
# exactly one slash whatever it was given: a path joined onto it without one
# would ask for something beside the site instead of inside it.
SITE_URL="${SITE_URL:-https://wolfgung.github.io/Marketplace-Test-Automation-Framework/}"
SITE_URL="${SITE_URL%/}/"

# A prior run that died mid-way can leave either of these behind; this one
# starts clean rather than building on top of them.
rm -rf "$RESULTS" "$SITE"

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

# True when the file $1 holds JSON whose top level is $2: an "object" or an
# "array". Parsing alone is not enough: `null` parses, and Allure 2.30.0 stops
# with a NullPointerException when that is what history.json holds, so a
# history file has to be of the shape Allure itself writes there.
json_of_shape() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path, shape = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if isinstance(value, dict if shape == "object" else list) else 1)
PY
}

# `RESET_SHOWCASE_HISTORY` is a documented, off-by-default escape hatch: set
# it and the trend starts over from this publication instead of carrying the
# previous one forward. It exists for exactly one situation — the published
# history needs to be discarded on purpose (contaminated by a run that was
# never a real CI publication, say) — and it is meant to be set for exactly
# one run and then unset again, both as deliberate, explained commits; it is
# not a normal knob left on. With it set, the published site is not even asked.
if [ -n "${RESET_SHOWCASE_HISTORY:-}" ]; then
  echo "build-showcase: RESET_SHOWCASE_HISTORY is set — starting the Allure trend over from this run" >&2
else
  # The previous publication's history, read back file by file from the site
  # it was deployed to. Allure uses each file on its own, so one that is
  # missing costs only its part of the trend. Any of them is allowed to be
  # missing, and so is the site: the very first publication has no history, a
  # runner can fail to reach the site, and either must degrade to a report
  # with no trend rather than to a broken run. What does arrive is written
  # into place only once it has been checked, so a body that is not what
  # Allure wrote — an error page served with a 200, a download cut short —
  # never reaches the report as if it were history.
  mkdir -p "$RESULTS/history"
  carried=0
  for entry in history:object history-trend:array duration-trend:array \
               categories-trend:array retry-trend:array; do
    name="${entry%%:*}"
    shape="${entry#*:}"
    url="${SITE_URL}report/history/$name.json"
    part="$RESULTS/history/$name.json.part"
    status=0
    code="$(curl --silent --show-error --location --retry 2 --max-time 30 \
      --output "$part" --write-out '%{http_code}' "$url")" || status=$?
    if [ "$status" -ne 0 ] && [ "$code" = "000" ]; then
      # No HTTP answer at all: a DNS failure, a refused connection, a timeout.
      # The other files live on the same site and would fail the same way.
      rm -f "$part"
      echo "build-showcase: $SITE_URL did not answer (curl exit $status), so no history comes from it" >&2
      break
    elif [ "$status" -ne 0 ] || [ "$code" != "200" ]; then
      echo "build-showcase: $url came back as HTTP $code (curl exit $status) — left out" >&2
    elif ! json_of_shape "$part" "$shape"; then
      echo "build-showcase: $url is not the JSON $shape Allure writes there — left out" >&2
    else
      mv "$part" "$RESULTS/history/$name.json"
      carried=$((carried + 1))
      continue
    fi
    rm -f "$part"
  done
  if [ "$carried" -gt 0 ]; then
    echo "build-showcase: carried over $carried of 5 Allure history files from ${SITE_URL}report/history/"
  else
    rm -rf "$RESULTS/history"
    echo "build-showcase: no Allure history came back from ${SITE_URL}report/history/ — the report shows this run with no trend" >&2
  fi
fi

if [ -n "${ALLURE_BIN:-}" ]; then
  allure=("$ALLURE_BIN")
else
  allure=(npx -y "allure-commandline@$ALLURE_VERSION")
fi
"${allure[@]}" generate "$RESULTS" --clean -o "$SITE/report"

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
# recording was published while the page never referenced it. One list now,
# in `showcase/build.py`; `tests/unit/test_build_showcase_script.py` fails if
# a second one comes back here.
#
# `--traces "$TRACES"` is the same arrangement for the Playwright trace: one
# per end-to-end case is written by the run, `build_site` picks the purchase
# and writes it to `$SITE/media/checkout-trace.zip`, and this script never
# names a file. The rule that kept the video honest is not worth re-learning
# on a second artefact.
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" python showcase/build.py \
  --results "$RESULTS" --out "$SITE" \
  --revision "${GITHUB_SHA:-local}" \
  --run-url "${RUN_URL:-}" \
  --videos "$VIDEOS" \
  --traces "$TRACES"

mkdir -p "$SITE/assets" "$SITE/media"
cp showcase/assets/*.svg "$SITE/assets/"

# Harmless under a deployment from Actions, which serves the files as they are.
# Kept so the same directory still works served from a branch, where GitHub
# Pages would run Jekyll over it and drop every directory whose name starts
# with an underscore.
touch "$SITE/.nojekyll"
echo "build-showcase: the site is assembled in $SITE/"
