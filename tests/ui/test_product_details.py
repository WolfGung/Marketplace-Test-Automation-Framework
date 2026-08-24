import allure
import pytest

from ecom_taf.ui.pages import ProductDetailsPage


@allure.epic("UI")
@allure.feature("Product details")
@pytest.mark.ui
def test_product_details_show_name_and_price(product_details_page: ProductDetailsPage) -> None:
    product_details_page.open_by_id(1)

    assert product_details_page.name()
    assert "rs." in product_details_page.price().lower()
