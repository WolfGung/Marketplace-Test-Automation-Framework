.PHONY: install test test-api test-ui test-e2e test-smoke test-stand test-public stand report lint

install:
	python3 -m pip install -e ".[dev,stand]"
	python3 -m playwright install chromium

test:
	pytest --alluredir=allure-results

test-api:
	pytest -m api --alluredir=allure-results

test-ui:
	pytest -m ui --alluredir=allure-results

test-e2e:
	pytest -m e2e --alluredir=allure-results

test-smoke:
	pytest -m smoke --alluredir=allure-results

test-stand:
	pytest tests/stand

# The drift check: the public site, read-only cases only.
test-public:
	TEST_ENV=prod pytest -m "smoke and not destructive" --alluredir=allure-results

# The stand on its own, for looking at it or for pointing another tool at it.
stand:
	uvicorn stand.app.main:app --port 8092

report:
	allure serve allure-results

lint:
	ruff check src tests showcase scripts stand
