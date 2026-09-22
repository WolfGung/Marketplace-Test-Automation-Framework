FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEADLESS=true \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium

COPY tests ./tests
# Not decoration, and not "the rest of the repository" either -- each of these
# is something the suite reads at runtime, and the image collected nothing at
# all without them:
#   allure/     the failure grouping that `tests/conftest.py` copies into every
#               results directory; without it a containerised run produces a
#               report with an empty Categories tab.
#   showcase/   imported by `tests/unit/test_showcase_build.py` and
#               `test_showcase_merge.py`, and read by `test_showcase_figures.py`
#               (the diagrams and the cover template it checks the numbers in).
#   scripts/    read by `tests/unit/test_publish_showcase_script.py`.
# pytest collects the whole `tests/` tree before it applies `-m`, so a missing
# import in `tests/unit` aborted the session before a single API test ran --
# `-m api` inside the container failed on a file that has nothing to do with
# the API. Found by running it, not by reading it.
COPY allure ./allure
COPY showcase ./showcase
COPY scripts ./scripts
COPY .env.example ./.env.example

# The API layer by default: it is the one layer that needs no browser, no
# display and no probe of somebody else's site, so `docker compose run --rm
# tests` works everywhere. The browser layers are one argument away and the
# README says so.
CMD ["pytest", "-m", "api", "--alluredir=allure-results"]
