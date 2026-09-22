"""The suite starts the stand only when it is the target, and never registers an account unannounced."""
from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from tests.conftest import _answers, _stand_address, _unmarked_account_creators


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


class _Item:
    """A collected test, as much of one as the guard reads.

    The guard asks an item two questions -- what is in its fixture closure, and
    what `destructive` resolves to for it -- so a stub that answers those two
    is the whole of what it needs. Driving real collection to produce a case
    for each shape would cost a subprocess per shape and prove nothing extra.
    """

    def __init__(self, nodeid: str, fixturenames: tuple[str, ...], markers: tuple[str, ...] = ()) -> None:
        self.nodeid = nodeid
        self.fixturenames = fixturenames
        self._markers = markers

    def get_closest_marker(self, name: str) -> SimpleNamespace | None:
        # pytest hands back a marker object or None, and the guard only asks
        # which of the two it got. `pytest.Mark` itself is private, so a stand-in
        # carrying the name keeps this stub out of pytest's internals.
        return SimpleNamespace(name=name) if name in self._markers else None


def test_a_test_that_registers_an_account_without_the_marker_is_reported() -> None:
    """The public site must never be asked to create an account by accident."""
    offender = _Item("tests/ui/test_auth.py::test_login", ("registered_user", "page"))

    assert _unmarked_account_creators([offender]) == [offender.nodeid]


def test_a_marked_creator_and_a_test_that_creates_nothing_are_not_reported() -> None:
    """The guard names what is wrong with a session, and nothing else.

    Both halves matter. A guard that reported a marked test would teach
    everyone to work around it; a guard that reported a read-only test would
    push `destructive` onto cases the drift check is meant to run.
    """
    marked = _Item(
        "tests/api/test_account_api.py::test_update_user_account",
        ("registered_user", "account_api"),
        markers=("api", "destructive"),
    )
    reader = _Item("tests/api/test_products_api.py::test_products_list", ("products_api",), markers=("api",))

    assert _unmarked_account_creators([marked, reader]) == []
