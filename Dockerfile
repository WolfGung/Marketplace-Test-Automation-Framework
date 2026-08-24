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
COPY .env.example ./.env.example

CMD ["pytest", "-m", "api or smoke", "--alluredir=allure-results"]
