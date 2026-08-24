.PHONY: install test test-api test-ui test-e2e test-smoke report lint

install:
	python3 -m pip install -e ".[dev]"
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

report:
	allure serve allure-results

lint:
	ruff check src tests
