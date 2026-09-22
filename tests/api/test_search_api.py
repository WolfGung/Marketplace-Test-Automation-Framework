import allure
import pytest

from ecom_taf.api import ProductsApi


@allure.epic("API")
@allure.feature("Search")
@allure.severity(allure.severity_level.NORMAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /searchProduct")
@pytest.mark.api
@pytest.mark.parametrize("query", ["top", "tshirt", "jean"])
def test_search_product_returns_matches(products_api: ProductsApi, query: str) -> None:
    result = products_api.search(query)
    catalog = products_api.parse_products(result)

    assert catalog.response_code == 200
    assert catalog.products
    assert all(product.name and product.price for product in catalog.products)


@allure.epic("API")
@allure.feature("Search")
@allure.severity(allure.severity_level.MINOR)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /searchProduct")
@pytest.mark.api
@pytest.mark.negative
def test_search_product_without_parameter(products_api: ProductsApi) -> None:
    result = products_api.search(None)

    assert result.response_code == 400
    assert "missing" in (result.message or "").lower()
