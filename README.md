# Marketplace Test Automation Framework

A test automation framework built from scratch for an online shop: API and browser tests that run in CI on every push, against a live storefront rather than a mock.

[![CI](https://github.com/WolfGung/Marketplace-Test-Automation-Framework/actions/workflows/ci.yml/badge.svg)](https://github.com/WolfGung/Marketplace-Test-Automation-Framework/actions/workflows/ci.yml)
[![live report](https://img.shields.io/badge/live%20report-Allure-brightgreen)](https://wolfgung.github.io/Marketplace-Test-Automation-Framework/report/)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![license: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

The suite covers three layers of the same shop: an API test suite for the rules behind the data — the catalogue, search, accounts and the answer each gives to input it should reject; browser tests for what only a customer can see; and end-to-end tests that follow a checkout flow from an empty cart to a placed order. Every run publishes an Allure report holding each case, its steps and the trend across runs, so what the suite did can be read without cloning it.

## Coverage

| What is checked | Checks | Where |
| --- | --- | --- |
| The REST API | 14 | `tests/api` |
| The browser | 8 | `tests/ui` |
| End to end, across both doors | 2 | `tests/e2e` |
| The application under test | 24 | the three rows above |
| Of those, the smoke set | 5 | `-m smoke` |

Counted by `pytest --collect-only`, and pinned by `tests/unit/test_showcase_figures.py` so a number here cannot drift away from the suite it describes.

Those are the checks of the marketplace, and they are the only ones counted — here, on the published page, and in the figures. The project also carries checks over its own tooling in [`tests/unit/`](tests/unit): its settings, the diagnostics captured when a browser test fails, the report's failure grouping, the build of the published page, and the pins that keep every number above honest. They are deliberately left out of the arithmetic, because they prove nothing about the application under test.

A check sits at the lowest layer that can still prove the thing that matters. Product listings, search results, account creation and deletion and the answers each gives to input it should reject are data rules, so they are asserted against the REST API, where a failure names its own cause. Only behaviour a person can see is driven through a browser. The end-to-end pair exists because the purchase is the one flow whose whole value is that the separate parts hold together.

Start with the evidence: **[the live Allure report](https://wolfgung.github.io/Marketplace-Test-Automation-Framework/report/)** holds every case, its steps and the trend across runs, and **[the project page](https://wolfgung.github.io/Marketplace-Test-Automation-Framework/)** — generated from the run that produced the numbers on it — carries a recording of the purchase running front to back and **[the Playwright trace of that same purchase](https://trace.playwright.dev/?trace=https://wolfgung.github.io/Marketplace-Test-Automation-Framework/media/checkout-trace.zip)**, which can be stepped through action by action with the page's DOM at each step.

[![The overview of the published Allure report: 24 test cases, 100% passing, split by suite into 14 in tests.api, 8 in tests.ui and 2 in tests.e2e, beside a trend that is green across every publication before it. Categories reads "0 items total" and Executors says there is no information about test executors.](allure-report-screenshot.png)](https://wolfgung.github.io/Marketplace-Test-Automation-Framework/report/)

That is the published report, photographed from what is actually on `gh-pages`, and the two empty panels are part of what it says. Categories holds nothing because publication waits for all three test jobs, so the run that publishes is a passing one and has no failures to group; Executors is empty because the pipeline writes no executor file. The trend beside them is real: it carries over from the previous publication on every run.

[![The pipeline's run page on github.com, read logged out: a run of the CI workflow on main under a green check, Status reading Success beside the commit that started it, and its jobs both listed down the side and drawn as a graph — the storefront probe, the API suite, the framework's own checks, the browser suite, the cross-browser job it skipped, and the publish step.](showcase/images/ci-run.png)](https://github.com/WolfGung/Marketplace-Test-Automation-Framework/actions/runs/35781319068)

That is the run the CI badge at the top of this page points at, photographed from the public run page by `PYTHONPATH=. python scripts/make-assets.py --only ci-run --ci-run <run url>`, which reads the status off the page and refuses to photograph a run that is not green.

[![Three bands. At the top the three test directories. Below them the code every test reuses: the HTTP client and the API resources, the page objects, the typed models, the per-run data factory and the settings. At the bottom the application under test, drawn as somebody else's system: the marketplace and its REST API. The API tests reach the API through the client, the browser tests reach the site through Playwright driving Chromium, and the end-to-end path runs down the middle through both doors at once. The figure states a case count for each directory; open it to read them.](showcase/assets/architecture.svg)](showcase/assets/architecture.svg)

Tests hold the assertions; everything reusable sits below them, so a change in the application lands in one file. The end-to-end path is the one route that crosses both doors. [Open the diagram at full size.](showcase/assets/architecture.svg)

## Application Under Test

Tests run against the public demo marketplace **[Automation Exercise](https://www.automationexercise.com/)**.

It is a good fit for this portfolio project because it exposes:

- a full storefront (auth, catalog, search, cart, checkout)
- a documented [REST API](https://www.automationexercise.com/api_list) for products, brands, search and accounts
- realistic API/UI cross-validation scenarios

This is a third-party public site. Tests create disposable accounts and delete them after use. Occasional flakiness from ads, rate limits or downtime is expected. The pipeline acts on that: every run first probes the storefront, and the browser suite runs only when the probe answers HTTP 200 — otherwise the run states which status it got and that the browser layer was skipped for it, rather than reporting a red suite the application did not cause. The API suite is never gated, because there a failure is the result and not an excuse.

## Tech Stack

- **Python 3.11+**
- **Pytest**
- **Playwright**
- **REST API** (`httpx`)
- **Allure Report**
- **Docker**
- **CI/CD** (GitHub Actions)

## Four decisions that keep it maintainable

**API responses are parsed into typed models, not read as dictionaries.** The catalogue and the search results go through `ProductsResponse` and `Product` in [`src/ecom_taf/models/`](src/ecom_taf/models) before a test asserts anything about them, and a registration travels the same way in the other direction through `UserAccount`. A field that is renamed, dropped or returned with the wrong type fails there, naming the field, instead of surfacing three assertions later as a `KeyError` — or as a comparison against `None` that happens to pass.

**One fact is checked through two doors.** [`tests/e2e/test_api_ui_product_consistency.py`](tests/e2e/test_api_ui_product_consistency.py) reads a product from the REST API, opens the same product in the browser and compares the name and the price. Both layers can be green while the two disagree; that disagreement is what a customer sees, and neither suite on its own can catch it.

**The suite is a polite guest on a site it does not own.** The `registered_user` fixture in [`tests/conftest.py`](tests/conftest.py) creates a disposable account through the API, hands it to the test and deletes it afterwards, so a run leaves the application as it found it. That is also why the hook that captures a failure screenshot is written never to raise: a crashed session skips teardown, and skipped teardown means an account left behind on somebody else's site.

**Per-run data comes from a factory, not from constants.** [`src/ecom_taf/data/user_factory.py`](src/ecom_taf/data/user_factory.py) builds a fresh account for every test that needs one, address and all. A suite pinned to a constant email passes once and then fails on "already registered", and the usual repair — deleting the record by hand between runs — is a step that cannot exist inside a pipeline.

## Architecture

```
src/ecom_taf/          # reusable framework (not tests)
  api/                 # HTTP client + resource APIs
  config/              # environment-based settings
  data/                # factories / test data builders
  models/              # typed payloads
  ui/pages/            # Page Object Model
tests/
  api/                 # contract / resource tests
  ui/                  # browser tests
  e2e/                 # business flows + API/UI checks
  unit/                # checks of this framework, not of the marketplace
```

That split is the four decisions above in directory form: a test module holds assertions and nothing else, everything a test reuses sits under `src/ecom_taf/` where a change in the application lands once, and `tests/unit/` checks that framework rather than the marketplace.

Business status codes for this AUT often live in JSON `responseCode` even when HTTP status is 200. The API client normalizes that so tests assert on the real result, not only the transport layer.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
```

## Run tests

```bash
# all tests
pytest

# layers
pytest -m api
pytest -m ui
pytest -m e2e
pytest -m smoke

# Allure results
pytest --alluredir=allure-results

# record the end-to-end run: a WebM video and a Playwright trace, one of each
# per e2e case, under videos/ and traces/
RECORD_VIDEO=true pytest -m e2e
playwright show-trace traces/checkout-test_logged_in_user_can_place_an_order.zip

# Allure CLI is not installed via pip. You need Java + Allure 2, then:
allure serve allure-results
```

Useful Make targets: `make install`, `make test`, `make test-api`, `make test-ui`, `make test-e2e`, `make test-smoke`, `make report`, `make lint`.

## Docker

One command, and it needs nothing on the machine but Docker — no Python, no Playwright, no browser:

```bash
docker compose run --rm tests
```

The first run builds the image (Python 3.12, this framework, Chromium and the system libraries it needs: a few minutes, roughly 3 GB on disk) and then runs the API layer, writing Allure results to `./allure-results` through the bind mount declared in `docker-compose.yml`. The API layer is the default because it is the one layer that needs no browser, no display and no reachable storefront to be worth running. Pass `--build` to rebuild the image after changing the code.

Any other selection is one argument away, and the browser layers run in the same container because Chromium is already in the image:

```bash
docker compose run --rm tests pytest -m ui --alluredir=allure-results
docker compose run --rm tests pytest tests/unit          # the framework's own checks
```

Two things worth knowing, both found by running it rather than by reading it. The container runs as root, so `allure-results/` and everything in it belongs to root on the host — `sudo chown -R "$USER" allure-results` if a local run has to write into the same directory afterwards. And the image copies `allure/`, `showcase/` and `scripts/` in as well as `tests/`: pytest imports the whole `tests/` tree before `-m` selects anything from it, so while those were missing, even `-m api` stopped at collection on an import that has nothing to do with the API.

## Configuration

Every setting in the project is here: `src/ecom_taf/config/settings.py` reads
these names and nothing else, `.env.example` lists the same set, and each is
read from the environment or from a `.env` beside it.

| Variable | Default | Description |
| --- | --- | --- |
| `TEST_ENV` | `prod` | Named environment from `environments.yaml` |
| `BASE_URL` | `https://www.automationexercise.com` | Storefront |
| `API_BASE_URL` | `https://www.automationexercise.com/api` | REST API |
| `HEADLESS` | `true` | Playwright headless mode |
| `BROWSER` | `chromium` | `chromium`, `firefox` or `webkit` |
| `SLOW_MO_MS` | `0` | Pause between Playwright actions, for watching a run |
| `DEFAULT_TIMEOUT_MS` | `15000` | Playwright's per-action timeout |
| `HTTP_TIMEOUT_S` | `20` | `httpx` timeout for the API layer |
| `RECORD_VIDEO` | `false` | Record the end-to-end cases: a WebM and a Playwright trace each |
| `VIDEO_DIR` | `videos` | Where those recordings are written |
| `TRACE_DIR` | `traces` | Where those traces are written |

## Markers

`api`, `ui`, `e2e`, `smoke`, `negative`, `integration`

## What the report shows

Every case carries an `epic` and a `feature`, so the report's **Behaviors** view is the suite read by what it covers — API, UI and E2E, and under each of them Account, Login, Products, Brands, Search, Cart, Checkout — rather than by the directory the file happens to live in.

Every case also carries a **severity**, and it means one thing: how much the defect that case would catch costs. The purchase is `blocker`. An account that cannot be created, a catalogue that does not answer, a sign-in that does not work and a wrong password that is accepted are `critical`. Input validation and unsupported methods are `minor`. A case does not get a high severity for having been difficult to write.

And every case links the page or the documented endpoint it drives, so a failure in the report is one click from the thing that failed.

## Cross-browser

The engine is a setting (`BROWSER`, read into `Settings.browser`), so the whole browser suite runs on Firefox or WebKit without a code change:

```bash
BROWSER=firefox pytest -m "ui or e2e"
```

CI has a `browsers` job that does exactly that on all three engines, and it runs **only on manual dispatch** — not on a push, not on the schedule. The application under test belongs to somebody else and the suite creates real accounts on it; no assertion here is about how a page renders in one engine versus another, so running every push three times over would triple that traffic to learn nothing. It is a question worth asking deliberately — after a Playwright upgrade, when a locator changes — which is when the button gets pressed.

## Related work

Two more repositories from the same portfolio:

- **[Toolshop-Test-Automation-Framework](https://github.com/WolfGung/Toolshop-Test-Automation-Framework)** — a test automation framework built from scratch for an online shop: API, browser and end-to-end cases against a public demo shop or a local Docker stand, with test design documents.
- **[Web-Scraping-Automation-Framework](https://github.com/WolfGung/Web-Scraping-Automation-Framework)** — a scraper that collects two practice sites over HTTP and through a browser, detects changes between nightly runs and publishes the data, the change report and the test report.

## Hire me

I take short, well-defined jobs: a test automation framework from scratch, an API test suite for an existing backend, end-to-end tests for a critical flow, fixing flaky tests and reducing run time, setting up CI for existing tests, scrapers and data pipelines. Profile on Guru: [https://www.guru.com/freelancers/pavel-zhukov-atum](https://www.guru.com/freelancers/pavel-zhukov-atum). Time zone UTC+2; I work in writing.
