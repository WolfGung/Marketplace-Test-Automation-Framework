from ecom_taf.ui.pages.base_page import BasePage


class HomePage(BasePage):
    path = "/"

    def is_loaded(self) -> bool:
        return self.page.locator("img[alt='Website for automation practice']").first.is_visible()

    def view_product(self, product_id: int) -> None:
        self.safe_click(self.page.locator(f"a[href='/product_details/{product_id}']").first)
