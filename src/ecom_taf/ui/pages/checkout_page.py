from ecom_taf.ui.pages.base_page import BasePage


class CheckoutPage(BasePage):
    path = "/checkout"

    def place_order(self) -> None:
        self.safe_click(self.page.locator("a[href='/payment']"))

    def delivery_address(self) -> str:
        return self.visible_text(self.page.locator("#address_delivery"))
