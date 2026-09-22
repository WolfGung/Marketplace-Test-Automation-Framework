"""The suite starts the stand only when it is the target and nothing is listening yet."""
from __future__ import annotations

import socket

import pytest

from tests.conftest import _answers, _stand_address


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://127.0.0.1:8092", ("127.0.0.1", 8092)),
        ("http://localhost:9000", ("localhost", 9000)),
        ("https://www.automationexercise.com", None),
        ("http://stand:8092", None),
    ],
)
def test_only_a_loopback_target_is_something_the_suite_would_start(base_url, expected) -> None:
    assert _stand_address(base_url) == expected


def test_a_closed_port_does_not_answer_and_an_open_one_does() -> None:
    port = _free_port()
    assert _answers(f"http://127.0.0.1:{port}") is False
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        assert _answers(f"http://127.0.0.1:{port}", timeout=0.5) is False  # listening but not HTTP: still no answer


def test_every_test_that_registers_an_account_is_marked_destructive() -> None:
    """The public site must never be asked to create an account by accident."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in sorted(root.glob("*/test_*.py")):
        if path.parent.name in {"unit", "stand"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"((?:@pytest\.mark\.\w+\n)+)def (test_\w+)\(([^)]*)\)", text):
            markers, name, params = match.groups()
            body = text.split(name, 1)[1].split("\ndef ", 1)[0]
            uses_account = "registered_user" in params or "account_api.create_account" in body
            if uses_account and "destructive" not in markers:
                offenders.append(f"{path.relative_to(root)}::{name}")
    assert not offenders, f"tests that create accounts without the destructive marker: {offenders}"
