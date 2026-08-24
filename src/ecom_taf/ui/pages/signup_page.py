from __future__ import annotations

import allure

from ecom_taf.models.user import UserAccount
from ecom_taf.ui.pages.base_page import BasePage


class SignupPage(BasePage):
    path = "/signup"

    def complete_account_form(self, user: UserAccount) -> None:
        with allure.step("Submit account information"):
            title_value = "Mr" if user.title == "Mr" else "Mrs"
            self.page.locator(f"input[value='{title_value}']").check()
            self.fill(self.page.locator("[data-qa='password']"), user.password)
            self.page.locator("[data-qa='days']").select_option(user.birth_date)
            self.page.locator("[data-qa='months']").select_option(user.birth_month)
            self.page.locator("[data-qa='years']").select_option(user.birth_year)
            self.fill(self.page.locator("[data-qa='first_name']"), user.firstname)
            self.fill(self.page.locator("[data-qa='last_name']"), user.lastname)
            self.fill(self.page.locator("[data-qa='company']"), user.company)
            self.fill(self.page.locator("[data-qa='address']"), user.address1)
            self.fill(self.page.locator("[data-qa='address2']"), user.address2)
            self.page.locator("[data-qa='country']").select_option(user.country)
            self.fill(self.page.locator("[data-qa='state']"), user.state)
            self.fill(self.page.locator("[data-qa='city']"), user.city)
            self.fill(self.page.locator("[data-qa='zipcode']"), user.zipcode)
            self.fill(self.page.locator("[data-qa='mobile_number']"), user.mobile_number)
            self.click(self.page.locator("[data-qa='create-account']"))

    def account_created_message(self) -> str:
        return self.visible_text(self.page.locator("[data-qa='account-created']"))

    def continue_after_created(self) -> None:
        self.click(self.page.locator("[data-qa='continue-button']"))
