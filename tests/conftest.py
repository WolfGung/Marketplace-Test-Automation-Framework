from __future__ import annotations

from pathlib import Path

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

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


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def http_client() -> HttpClient:
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


@pytest.fixture
def context(browser: Browser, settings: Settings, request: pytest.FixtureRequest) -> BrowserContext:
    kwargs = {
        "base_url": settings.base_url,
        "viewport": {"width": 1440, "height": 900},
        "ignore_https_errors": True,
    }
    recording = settings.record_video and request.node.get_closest_marker("e2e") is not None
    if recording:
        kwargs["record_video_dir"] = settings.video_dir
        kwargs["record_video_size"] = {"width": 1440, "height": 900}
    context = browser.new_context(**kwargs)
    context.set_default_timeout(settings.default_timeout_ms)
    yield context
    # The page fixture tears down first and closes the page, so `context.pages`
    # is empty by now — the handle has to be captured while the page still
    # exists. The page fixture stashes it for us.
    video = getattr(request.node, "_video", None)
    context.close()  # Playwright only finalises the file when the context closes
    if video is None:
        return
    try:
        source = Path(video.path())
        target = source.with_name(f"checkout-{request.node.name}.webm")
        source.rename(target)
        allure.attach.file(str(target), name="video", attachment_type=allure.attachment_type.WEBM)
    except Exception:  # a recording is never worth failing a green test over
        pass


@pytest.fixture
def page(context: BrowserContext, request: pytest.FixtureRequest) -> Page:
    page = context.new_page()
    yield page
    request.node._video = page.video  # None when recording is off
    page.close()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    page = item.funcargs.get("page")
    if page is None:
        return
    allure.attach(
        page.screenshot(full_page=True),
        name="failure-screenshot",
        attachment_type=allure.attachment_type.PNG,
    )
    allure.attach(
        page.content(),
        name="failure-html",
        attachment_type=allure.attachment_type.HTML,
    )


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
