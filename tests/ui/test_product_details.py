import allure
import pytest

from ecom_taf.ui.pages import ProductDetailsPage


@allure.epic("UI")
@allure.feature("Product details")
@allure.severity(allure.severity_level.NORMAL)
@allure.link("https://www.automationexercise.com/product_details/1", name="Page under test: /product_details/1")
@pytest.mark.ui
def test_product_details_show_name_and_price(product_details_page: ProductDetailsPage) -> None:
    product_details_page.open_by_id(1)

    assert product_details_page.name()
    assert "rs." in product_details_page.price().lower()
