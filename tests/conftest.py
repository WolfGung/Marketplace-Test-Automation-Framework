from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import urlopen

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Video, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ecom_taf.api import AccountApi, HttpClient, ProductsApi
from ecom_taf.config import Settings, get_settings
from ecom_taf.data import UserFactory
from ecom_taf.models.user import UserAccount
from ecom_taf.ui.pages import (
    AuthPage,
    CartPage,
    CheckoutPage,
    HomePage,
    PaymentPage,
    ProductDetailsPage,
    ProductsPage,
    SignupPage,
)

#: Holds the finished-page's Video handle across the `page` -> `context` teardown
#: boundary. A StashKey rather than a raw node attribute so it can't collide with
#: anything another fixture or plugin stores on the same node.
VIDEO_KEY: pytest.StashKey[Video | None] = pytest.StashKey()


#: Failure categories, kept beside the suite and read by Allure out of the
#: results directory. `allure generate` has no flag for it: a copy has to be
#: in the results themselves, or the report comes out with an empty
#: Categories tab regardless of what the suite actually produced.
CATEGORIES = Path(__file__).resolve().parents[1] / "allure" / "categories.json"


def copy_categories_into(results_dir: Path) -> None:
    """Put the failure grouping where Allure reads it from.

    Allure only groups failures when `categories.json` sits in the results
    directory, so a file that lives in the repository and never travels with a
    run is a promise the report cannot keep.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CATEGORIES, results_dir / "categories.json")


def _will_drive_a_browser(items: list[pytest.Item]) -> bool:
    """Whether anything this session is about to run opens a browser.

    Read off the fixture closure rather than off the markers: `browser` is a
    session fixture that `page` requires and every page object fixture
    requires in turn, so a case reaches it however it was selected, and a case
    that stops asking for it stops counting here without anyone remembering to
    update a list of markers.
    """
    return any("browser" in item.fixturenames for item in items)


def _write_environment_properties(results_dir: Path, *, browser_used: bool) -> None:
    """Record what a run was tested against, for the report's Environment panel.

    Allure only populates that panel when `environment.properties` sits in the
    results directory — otherwise a published report shows a failure without
    saying which site, or which Python produced it, and a third party reading
    it later has no way to tell.

    The panel states facts about the run, not the configuration the run was
    handed, and those are not the same thing. `Settings.browser` and
    `Settings.headless` always have values -- they default to chromium and
    headless -- but the `api` job never opens a browser, and a panel reading
    `api.Browser=chromium` told a reader something that did not happen. So the
    two browser keys are written only when this session will actually drive
    one, which is why this runs after collection rather than at session start:
    what a run will do is not known until its items are.

    In CI, this file is written independently by the `api` job and the `ui`
    job into their own separate `--alluredir`, and the showcase's publish step
    later merges both jobs' results into one directory. Two files with the same
    name and genuinely different content would let the later download of one
    job's artefact silently overwrite the other's, so every key is qualified
    with the job's own name -- `GITHUB_JOB`, which GitHub Actions sets to
    exactly `api` or `ui` -- whenever one is set. `showcase/merge.py` is what
    actually combines the two files; qualifying the keys here is what makes
    that combination a union instead of a collision. Outside CI there is only
    ever one job's results in play, so the keys are left bare, matching every
    environment.properties this project wrote before this qualification
    existed.
    """
    settings = get_settings()
    results_dir.mkdir(parents=True, exist_ok=True)
    job = os.getenv("GITHUB_JOB")
    prefix = f"{job}." if job else ""
    lines = [
        f"{prefix}BASE_URL={settings.base_url}",
        f"{prefix}API_BASE_URL={settings.api_base_url}",
    ]
    if browser_used:
        lines += [
            f"{prefix}Browser={settings.browser}",
            f"{prefix}Headless={settings.headless}",
        ]
    lines += [
        f"{prefix}Python={sys.version.split()[0]}",
        f"{prefix}CI={os.getenv('CI', 'false')}",
    ]
    (results_dir / "environment.properties").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def _prepare_reporting(results_dir: Path, *, browser_used: bool) -> None:
    """Write the categories file and the environment properties, degrading on failure.

    Same rule as `_attach_diagnostic` and `_capture_failure_diagnostics` below:
    reporting-adjacent setup must never take the run down. An unwritable
    `--alluredir`, a path that already exists as a file, a full disk, or a
    checkout missing `allure/categories.json` would otherwise abort the
    session before a single test runs — trading a plainer report for no
    report and no tests at all. The two writes are guarded independently so
    that one failing (a missing categories file, say) does not also cost the
    other (the environment panel).
    """
    try:
        copy_categories_into(results_dir)
    except Exception as exc:
        warnings.warn(f"could not write categories.json into {results_dir}: {exc!r}", stacklevel=2)

    try:
        _write_environment_properties(results_dir, browser_used=browser_used)
    except Exception as exc:
        warnings.warn(f"could not write environment.properties into {results_dir}: {exc!r}", stacklevel=2)


def pytest_collection_finish(session: pytest.Session) -> None:
    """Write the results directory's two companion files, once collection is in.

    Later than session start, and deliberately: the Environment panel is meant
    to describe the run, and whether this run opens a browser at all is a fact
    about its items. Both files are written here so that one of them failing
    still leaves the other -- which is what `_prepare_reporting` guards -- and
    both land long before the first test, which is all Allure needs: it reads
    them out of the results directory when the report is generated.

    `pytest_collection_finish` and not `pytest_collection_modifyitems`, which
    is the hook this obviously wants to be. A conftest's implementation of
    that one is called *before* pytest deselects by `-m`, so under the CI
    command `pytest -m api` it is handed the browser cases as well and would
    answer "yes, a browser" for the one job that opens none -- the exact claim
    this is here to stop. `session.items` at this point is what will actually
    run.
    """
    if session.config.option.collectonly:
        return
    configured = session.config.getoption("--alluredir", default=None)
    if configured:
        _prepare_reporting(
            Path(configured), browser_used=_will_drive_a_browser(session.items)
        )


def _attach_diagnostic(body: Any, *, name: str, attachment_type: Any) -> None:
    """Best-effort Allure attach: a failure here must never propagate.

    Used for every attachment produced while a test is otherwise green (or already
    failed for its own reason) — the diagnostic is a courtesy, never a reason to
    take the run down.
    """
    try:
        allure.attach(body, name=name, attachment_type=attachment_type)
    except Exception as exc:
        warnings.warn(f"could not attach {name!r} to Allure: {exc!r}", stacklevel=2)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


def _stand_address(base_url: str) -> tuple[str, int] | None:
    """Host and port when the target is this machine, else None.

    Only a loopback target is something this suite would start itself: a
    hostname like `stand` (the compose service) or the public site is
    somebody else's process, answering or not.
    """
    parts = urlsplit(base_url)
    if parts.hostname not in {"127.0.0.1", "localhost"} or parts.port is None:
        return None
    return parts.hostname, parts.port


def _answers(url: str, timeout: float = 1.0) -> bool:
    """Whether an HTTP server answers at `url` with any status at all."""
    try:
        with urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def local_stand(settings: Settings):
    """Start the stand in this process when the suite targets it and nothing answers.

    A clean clone runs `make test` and expects green: the stand is part of the
    repository, so the suite starts it rather than asking the reader to open
    a second terminal. When something already listens on the port — the
    compose service, a stand started by hand, the CI job — it is used as is,
    exactly like the public site was. A target that is not loopback is never
    started here.
    """
    address = _stand_address(settings.base_url)
    if address is None or _answers(settings.base_url):
        yield None
        return
    import uvicorn  # the stand's dependencies are an extra: only a local run needs them

    from stand.app.main import create_app

    host, port = address
    server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True, name="local-stand")
    thread.start()
    deadline = time.monotonic() + 15
    while not _answers(settings.base_url, timeout=0.5):
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError(f"the stand did not start on {settings.base_url} within 15 s")
        time.sleep(0.2)
    yield server
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def http_client(local_stand) -> HttpClient:
    client = HttpClient()
    yield client
    client.close()


@pytest.fixture
def products_api(http_client: HttpClient) -> ProductsApi:
    return ProductsApi(http_client)


@pytest.fixture
def account_api(http_client: HttpClient) -> AccountApi:
    return AccountApi(http_client)


@pytest.fixture
def registered_user(account_api: AccountApi) -> UserAccount:
    user = UserFactory.build()
    result = account_api.create_account(user)
    assert result.response_code == 201, result.payload
    yield user
    account_api.delete_account(user.email, user.password)


@pytest.fixture(scope="session")
def playwright_runtime() -> Playwright:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright_runtime: Playwright, settings: Settings) -> Browser:
    launcher = getattr(playwright_runtime, settings.browser)
    browser = launcher.launch(headless=settings.headless, slow_mo=settings.slow_mo_ms)
    yield browser
    browser.close()


def _stop_tracing(context: BrowserContext, trace_dir: str, name: str) -> None:
    """Write the trace out, best-effort, before the context that holds it closes.

    A trace is a courtesy exactly as the recording is, so the same rule applies:
    it must never turn a green test red. `stop(path=...)` is what actually
    writes the zip — stopping without a path throws the recording away — and it
    has to happen while the context is still open, because the tracing
    machinery lives on the context.
    """
    target = Path(trace_dir) / f"checkout-{name}.zip"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        context.tracing.stop(path=str(target))
    except Exception as exc:  # a trace is never worth failing a green test over
        message = f"could not write the trace for {name}: {exc!r}"
        warnings.warn(message, stacklevel=2)
        _attach_diagnostic(message, name="trace-unavailable", attachment_type=allure.attachment_type.TEXT)


@pytest.fixture
def context(browser: Browser, settings: Settings, request: pytest.FixtureRequest, local_stand) -> BrowserContext:
    kwargs = {
        "base_url": settings.base_url,
        "viewport": {"width": 1440, "height": 900},
        "ignore_https_errors": True,
    }
    # One switch for both artefacts, and only for the end-to-end cases. A trace
    # per test is a pile of zip files nobody opens; the trace that earns its
    # disk is the one of the flow a reader would otherwise have to take on
    # trust, which is the same flow the video records.
    recording = settings.record_video and request.node.get_closest_marker("e2e") is not None
    if recording:
        kwargs["record_video_dir"] = settings.video_dir
        kwargs["record_video_size"] = {"width": 1440, "height": 900}
    context = browser.new_context(**kwargs)
    context.set_default_timeout(settings.default_timeout_ms)
    if recording:
        # Screenshots give the trace viewer its filmstrip, snapshots give it the
        # DOM at every action (which is the whole point: a reader can inspect
        # the page as it was, not just look at a picture of it), and sources
        # puts the test's own code beside the step that ran it.
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    yield context
    # The page fixture tears down first and closes the page, so `context.pages`
    # is empty by now — the handle has to be captured while the page still
    # exists. The page fixture stashes it for us.
    video = request.node.stash.get(VIDEO_KEY, None)
    if recording:
        _stop_tracing(context, settings.trace_dir, request.node.name)
    context.close()  # Playwright only finalises the file when the context closes
    if video is None:
        return
    try:
        source = Path(video.path())
        target = source.with_name(f"checkout-{request.node.name}.webm")
        source.rename(target)
        allure.attach.file(str(target), name="video", attachment_type=allure.attachment_type.WEBM)
    except Exception as exc:  # a recording is never worth failing a green test over
        # A print to stderr is invisible under this project's own invocation
        # (`-q`, no `-s`/`-rA`): a pytest warning surfaces in the default summary
        # under `-q` too, and the Allure attachment travels with the report that a
        # later step publishes — that is where anyone chasing a missing video will
        # actually be looking.
        message = f"could not attach recording for {request.node.name}: {exc!r}"
        warnings.warn(message, stacklevel=2)
        _attach_diagnostic(message, name="video-unavailable", attachment_type=allure.attachment_type.TEXT)


@pytest.fixture
def page(context: BrowserContext, request: pytest.FixtureRequest) -> Page:
    page = context.new_page()
    yield page
    request.node.stash[VIDEO_KEY] = page.video  # None when recording is off
    page.close()


#: Deliberately short and independent of `settings.default_timeout_ms`: this hook
#: runs after a test has already failed, so it must fail fast rather than block the
#: session for the full navigation timeout on top of the original failure.
DIAGNOSTIC_CAPTURE_TIMEOUT_MS = 5_000


def _capture_failure_diagnostics(page: Page) -> None:
    """Best-effort failure screenshot + HTML capture. Must never raise.

    Factored out of the hook so it can be exercised directly, with a stub page,
    from ``tests/unit/test_failure_diagnostics.py`` — a guard with no test for it
    is a guard that rots.
    """
    # Neither capture may be allowed to raise: a page already closed or a slow/dead
    # site must not turn a reported test failure into a crashed session (which would
    # skip fixture teardown, e.g. `registered_user`'s account cleanup, entirely).
    try:
        screenshot = page.screenshot(full_page=True, timeout=DIAGNOSTIC_CAPTURE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        _attach_diagnostic(
            f"Could not capture failure screenshot: {exc!r}",
            name="failure-screenshot-unavailable",
            attachment_type=allure.attachment_type.TEXT,
        )
        # `page.content()` takes no `timeout` argument, and nothing else bounds
        # it either: `set_default_timeout` looks like it should, but it does
        # not -- `Frame.content()` sends its request with no timeout
        # calculator at all in this Playwright version, so the default is
        # never consulted. Verified against a real hung page: with the page's
        # main thread blocked and a 500ms default timeout, `content()` still
        # returned after 7.81s while `screenshot(timeout=500)` raised at
        # 0.50s under the identical hang. That asymmetry is exactly what this
        # hook exists to avoid -- an unbounded diagnostic once killed a
        # session before teardown ran, leaving a live account behind on
        # somebody else's site. Since there is no genuine way to bound
        # `content()` here, the screenshot above is used as a canary instead:
        # a page that cannot produce a screenshot within
        # `DIAGNOSTIC_CAPTURE_TIMEOUT_MS` is a page that cannot be trusted to
        # serialise its DOM in that time either, so `content()` is skipped
        # entirely rather than attempted unbounded.
        _attach_diagnostic(
            "Skipped: the failure screenshot timed out, and page.content() has "
            "no timeout mechanism of its own in this Playwright version to "
            "bound it with -- calling it here would risk the same unbounded "
            "hang the screenshot timeout exists to avoid.",
            name="failure-html-skipped",
            attachment_type=allure.attachment_type.TEXT,
        )
        return
    except Exception as exc:
        _attach_diagnostic(
            f"Could not capture failure screenshot: {exc!r}",
            name="failure-screenshot-unavailable",
            attachment_type=allure.attachment_type.TEXT,
        )
    else:
        _attach_diagnostic(screenshot, name="failure-screenshot", attachment_type=allure.attachment_type.PNG)

    try:
        html = page.content()
    except Exception as exc:
        _attach_diagnostic(
            f"Could not capture failure HTML: {exc!r}",
            name="failure-html-unavailable",
            attachment_type=allure.attachment_type.TEXT,
        )
    else:
        _attach_diagnostic(html, name="failure-html", attachment_type=allure.attachment_type.HTML)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    page = item.funcargs.get("page")
    if page is None:
        return
    _capture_failure_diagnostics(page)


@pytest.fixture
def home_page(page: Page) -> HomePage:
    return HomePage(page)


@pytest.fixture
def auth_page(page: Page) -> AuthPage:
    return AuthPage(page)


@pytest.fixture
def signup_page(page: Page) -> SignupPage:
    return SignupPage(page)


@pytest.fixture
def products_page(page: Page) -> ProductsPage:
    return ProductsPage(page)


@pytest.fixture
def product_details_page(page: Page) -> ProductDetailsPage:
    return ProductDetailsPage(page)


@pytest.fixture
def cart_page(page: Page) -> CartPage:
    return CartPage(page)


@pytest.fixture
def checkout_page(page: Page) -> CheckoutPage:
    return CheckoutPage(page)


@pytest.fixture
def payment_page(page: Page) -> PaymentPage:
    return PaymentPage(page)
