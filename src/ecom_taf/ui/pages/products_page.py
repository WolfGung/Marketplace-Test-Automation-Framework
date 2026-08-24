from __future__ import annotations

import allure

from ecom_taf.ui.pages.base_page import BasePage


class ProductsPage(BasePage):
    path = "/products"

    def search(self, query: str) -> None:
        with allure.step(f"Search products: {query}"):
            self.fill(self.page.locator("#search_product"), query)
            self.click(self.page.locator("#submit_search"))

    def searched_products_title(self) -> str:
        return self.visible_text(self.page.locator(".features_items h2.title").first)

    def product_names(self) -> list[str]:
        return [text.strip() for text in self.page.locator(".productinfo p").all_inner_texts() if text.strip()]

    def add_first_product_to_cart(self) -> None:
        with allure.step("Add first product to cart"):
            self.page.locator(".productinfo a.add-to-cart").first.click()
            self.page.locator(".modal-content").wait_for(state="visible")

    def view_cart_from_modal(self) -> None:
        self.click(self.page.locator(".modal-content a[href='/view_cart']"))

    def continue_shopping(self) -> None:
        self.click(self.page.locator(".modal-footer .btn-success"))

    def open_product_details(self, product_id: int) -> None:
        self.safe_click(self.page.locator(f"a[href='/product_details/{product_id}']").first)
