from ecom_taf.ui.pages.base_page import BasePage


class CartPage(BasePage):
    path = "/view_cart"

    def product_names(self) -> list[str]:
        return [text.strip() for text in self.page.locator(".cart_description h4 a").all_inner_texts()]

    def quantities(self) -> list[str]:
        texts = self.page.locator(".cart_quantity button").all_inner_texts()
        return [text.strip() for text in texts if text.strip()]

    def proceed_to_checkout(self) -> None:
        self.click(self.page.locator("a.check_out"))

    def is_empty(self) -> bool:
        if self.page.locator("#empty_cart").is_visible():
            return True
        return self.page.locator("#cart_info tr").count() == 0
