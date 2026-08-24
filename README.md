# E-commerce Test Automation Framework

A production-style test automation framework for an e-commerce / marketplace application, built with **Python, Pytest and Playwright**.

The project demonstrates a scalable approach to automated testing across multiple layers — **UI, REST API and end-to-end flows** — with reusable test infrastructure, structured test data, reporting and CI/CD integration.

## Application Under Test

Tests run against the public demo marketplace **[Automation Exercise](https://www.automationexercise.com/)**.

It is a good fit for this portfolio project because it exposes:

- a full storefront (auth, catalog, search, cart, checkout)
- a documented [REST API](https://www.automationexercise.com/api_list) for products, brands, search and accounts
- realistic API/UI cross-validation scenarios

This is a third-party public site. Tests create disposable accounts and delete them after use. Occasional flakiness from ads, rate limits or downtime is expected.

## Tech Stack

- **Python 3.11+**
- **Pytest**
- **Playwright**
- **REST API** (`httpx`)
- **Allure Report**
- **Docker**
- **CI/CD** (GitHub Actions)

## Testing Approach

The framework covers:

- UI testing with Playwright
- REST API testing
- End-to-end business scenarios
- Page Object Model
- Pytest fixtures
- Parameterized tests
- Test data management
- API/UI integration scenarios
- Positive and negative testing
- Test reporting with Allure
- Containerized test execution
- CI/CD pipeline integration

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
```

The framework is designed with maintainability and scalability in mind:

- Clear separation between test layers
- Reusable fixtures and utilities
- Page Objects for UI interactions
- API clients for backend communication
- Centralized test configuration
- Environment-based configuration
- Independent and parameterized test scenarios
- Automated test execution in CI/CD

Business status codes for this AUT often live in JSON `responseCode` even when HTTP status is 200. The API client normalizes that so tests assert on the real result, not only the transport layer.

## Example E-commerce Scenarios

The test suite includes realistic marketplace workflows such as:

- User registration and authentication
- Product search and filtering
- Product details
- Shopping cart management
- Checkout
- Order creation
- API validation
- UI/API cross-validation
- Negative and boundary scenarios

## Project Goals

This project demonstrates practical **Senior SDET / Test Automation Engineering** skills rather than a collection of isolated automated tests.

The main focus is on:

- Test automation architecture
- Maintainable and reusable test code
- Multi-layer testing
- API + UI + E2E coverage
- CI/CD integration
- Test observability and reporting
- Scalable automation practices

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

# Allure CLI is not installed via pip. You need Java + Allure 2, then:
allure serve allure-results
```

Useful Make targets: `make install`, `make test-api`, `make test-ui`, `make test-e2e`, `make test`, `make report`.

## Docker

```bash
docker compose run --rm tests
```

By default the container runs API + smoke tests. Override the command to run a specific layer:

```bash
docker compose run --rm tests pytest -m api
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `TEST_ENV` | `prod` | Named environment from `environments.yaml` |
| `BASE_URL` | `https://www.automationexercise.com` | Storefront |
| `API_BASE_URL` | `https://www.automationexercise.com/api` | REST API |
| `HEADLESS` | `true` | Playwright headless mode |
| `BROWSER` | `chromium` | `chromium`, `firefox` or `webkit` |

## Markers

`api`, `ui`, `e2e`, `smoke`, `negative`, `integration`
