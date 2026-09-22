import allure
import pytest

from ecom_taf.ui.pages import ProductsPage


@allure.epic("UI")
@allure.feature("Search")
@allure.severity(allure.severity_level.NORMAL)
@allure.link("https://www.automationexercise.com/products", name="Page under test: /products")
@pytest.mark.ui
@pytest.mark.parametrize("query", ["Dress", "Tshirt"])
def test_product_search_returns_results(products_page: ProductsPage, query: str) -> None:
    products_page.open()
    products_page.search(query)

    assert "searched" in products_page.searched_products_title().lower()
    names = products_page.product_names()
    assert names
