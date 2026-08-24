from __future__ import annotations

import allure
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ecom_taf.config import get_settings


class BasePage:
    path = "/"

    def __init__(self, page: Page) -> None:
        self.page = page
        self.settings = get_settings()

    @property
    def url(self) -> str:
        return f"{self.settings.base_url}{self.path}"

    def open(self) -> None:
        with allure.step(f"Open {self.url}"):
            self.page.goto(self.url, wait_until="domcontentloaded")
            self.dismiss_overlays()

    def dismiss_overlays(self) -> None:
        """Public demo pages are often covered by ad iframes."""
        try:
            self.page.evaluate(
                """
                () => {
                  document.querySelectorAll("iframe, #ad_position_box, .adsbygoogle")
                    .forEach((el) => el.remove());
                }
                """
            )
        except Exception:
            pass

    def click(self, locator: Locator, *, timeout: int | None = None) -> None:
        self.dismiss_overlays()
        locator.click(timeout=timeout or self.settings.default_timeout_ms)

    def fill(self, locator: Locator, value: str) -> None:
        locator.fill(value)

    def visible_text(self, locator: Locator) -> str:
        locator.wait_for(state="visible", timeout=self.settings.default_timeout_ms)
        return locator.inner_text().strip()

    def go_to_products(self) -> None:
        self.click(self.page.locator("a[href='/products']").first)

    def go_to_cart(self) -> None:
        self.click(self.page.locator("a[href='/view_cart']").first)

    def go_to_login(self) -> None:
        self.click(self.page.locator("a[href='/login']").first)

    def logout(self) -> None:
        self.click(self.page.locator("a[href='/logout']").first)

    def logged_in_as(self) -> Locator:
        return self.page.locator("a", has_text="Logged in as")

    def wait_for_url_contains(self, fragment: str) -> None:
        self.page.wait_for_url(f"**{fragment}**", timeout=self.settings.default_timeout_ms)

    def safe_click(self, locator: Locator) -> None:
        try:
            self.click(locator)
        except PlaywrightTimeoutError:
            self.dismiss_overlays()
            locator.click(force=True)
