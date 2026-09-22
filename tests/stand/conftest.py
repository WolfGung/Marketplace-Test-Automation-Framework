"""Fixtures for the stand's own contract tests: an app per test, no browser."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from stand.app.main import create_app


@pytest.fixture
def client() -> TestClient:
    # A fresh app per test: the account store and the sessions live on the app,
    # so one test's account never leaks into the next.
    return TestClient(create_app())


@pytest.fixture
def account_form() -> dict[str, str]:
    return {
        "name": "Ada Lovelace",
        "email": "ada.lovelace.4242@example.com",
        "password": "Qwerty!234",
        "title": "Mrs",
        "birth_date": "10",
        "birth_month": "12",
        "birth_year": "1985",
        "firstname": "Ada",
        "lastname": "Lovelace",
        "company": "Analytical Engines",
        "address1": "1 Difference Street",
        "address2": "Suite 2",
        "country": "United States",
        "zipcode": "10001",
        "state": "New York",
        "city": "New York",
        "mobile_number": "2125550123",
    }
