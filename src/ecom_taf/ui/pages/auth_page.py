from __future__ import annotations

import allure

from ecom_taf.ui.pages.base_page import BasePage


class AuthPage(BasePage):
    path = "/login"

    def signup(self, name: str, email: str) -> None:
        with allure.step(f"Start signup for {email}"):
            self.fill(self.page.locator("[data-qa='signup-name']"), name)
            self.fill(self.page.locator("[data-qa='signup-email']"), email)
            self.click(self.page.locator("[data-qa='signup-button']"))

    def login(self, email: str, password: str) -> None:
        with allure.step(f"Log in as {email}"):
            self.fill(self.page.locator("[data-qa='login-email']"), email)
            self.fill(self.page.locator("[data-qa='login-password']"), password)
            self.click(self.page.locator("[data-qa='login-button']"))

    def login_error(self) -> str:
        return self.visible_text(self.page.locator("form").filter(has_text="Login").locator("p"))

    def signup_error(self) -> str:
        return self.visible_text(self.page.locator("form").filter(has_text="Signup").locator("p"))
