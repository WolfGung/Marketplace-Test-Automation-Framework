from __future__ import annotations

import allure

from ecom_taf.ui.pages.base_page import BasePage


class PaymentPage(BasePage):
    path = "/payment"

    def pay(
        self,
        *,
        name_on_card: str = "Test User",
        card_number: str = "4111111111111111",
        cvc: str = "123",
        expiry_month: str = "12",
        expiry_year: str = "2030",
    ) -> None:
        with allure.step("Submit payment details"):
            self.fill(self.page.locator("[data-qa='name-on-card']"), name_on_card)
            self.fill(self.page.locator("[data-qa='card-number']"), card_number)
            self.fill(self.page.locator("[data-qa='cvc']"), cvc)
            self.fill(self.page.locator("[data-qa='expiry-month']"), expiry_month)
            self.fill(self.page.locator("[data-qa='expiry-year']"), expiry_year)
            self.click(self.page.locator("[data-qa='pay-button']"))

    def order_placed_message(self) -> str:
        return self.visible_text(self.page.locator("[data-qa='order-placed']"))
