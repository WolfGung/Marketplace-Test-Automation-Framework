"""One account store for the REST API and the browser session, and the sessions themselves.

The suite creates an account through the API and then logs in through the
login form in the same test; nothing in the suite checks those two doors
separately, so if they read different stores the failure would surface as a
timeout on the "Logged in as" link with no test naming the real cause. Both
doors read and write the one `AccountStore` on the app.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

ACCOUNT_FIELDS = (
    "name", "email", "password", "title", "birth_date", "birth_month", "birth_year",
    "firstname", "lastname", "company", "address1", "address2", "country",
    "zipcode", "state", "city", "mobile_number",
)


class AccountStore:
    def __init__(self) -> None:
        self._accounts: dict[str, dict[str, str]] = {}

    def create(self, fields: dict[str, str]) -> bool:
        """Store a new account; False when the email is taken."""
        email = fields.get("email", "")
        if not email or email in self._accounts:
            return False
        self._accounts[email] = {name: fields.get(name, "") for name in ACCOUNT_FIELDS}
        return True

    def get(self, email: str) -> dict[str, str] | None:
        account = self._accounts.get(email)
        return dict(account) if account else None

    def verify(self, email: str, password: str) -> bool:
        account = self._accounts.get(email)
        return account is not None and account["password"] == password

    def update(self, fields: dict[str, str]) -> bool:
        email = fields.get("email", "")
        if email not in self._accounts:
            return False
        self._accounts[email].update({name: fields[name] for name in ACCOUNT_FIELDS if name in fields})
        return True

    def delete(self, email: str, password: str) -> bool:
        if not self.verify(email, password):
            return False
        del self._accounts[email]
        return True


@dataclass
class Session:
    email: str | None = None
    cart: dict[int, int] = field(default_factory=dict)
    pending_signup: dict[str, str] | None = None


class SessionStore:
    """Server-side sessions keyed by a cookie value; a fresh one per browser context."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, token: str | None) -> tuple[str, Session]:
        if token and token in self._sessions:
            return token, self._sessions[token]
        token = uuid.uuid4().hex
        self._sessions[token] = Session()
        return token, self._sessions[token]

    def count(self) -> int:
        """How many sessions are being held.

        A method rather than a test reaching into `_sessions`: what a test
        wants to know is how many sessions exist, and a store can answer that
        without publishing the dictionary it keeps them in.
        """
        return len(self._sessions)
