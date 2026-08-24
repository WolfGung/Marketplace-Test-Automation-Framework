from __future__ import annotations

import allure

from ecom_taf.ui.pages.base_page import BasePage


class ProductDetailsPage(BasePage):
    path = "/product_details/"

    def open_by_id(self, product_id: int) -> None:
        self.path = f"/product_details/{product_id}"
        self.open()

    def name(self) -> str:
        return self.visible_text(self.page.locator(".product-information h2"))

    def price(self) -> str:
        return self.visible_text(self.page.locator(".product-information span span"))

    def add_to_cart(self, quantity: int = 1) -> None:
        with allure.step(f"Add product to cart, qty={quantity}"):
            qty = self.page.locator("#quantity")
            qty.fill(str(quantity))
            self.click(self.page.locator("button.cart"))
            self.page.locator(".modal-content").wait_for(state="visible")
