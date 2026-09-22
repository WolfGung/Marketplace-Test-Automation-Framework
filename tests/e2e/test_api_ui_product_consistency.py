import allure
import pytest

from ecom_taf.api import ProductsApi
from ecom_taf.ui.pages import ProductDetailsPage


@allure.epic("E2E")
@allure.feature("API/UI cross-validation")
@allure.severity(allure.severity_level.CRITICAL)
@allure.link("https://www.automationexercise.com/product_details/1", name="Page under test: /product_details/1")
@pytest.mark.e2e
@pytest.mark.integration
def test_product_details_match_api_catalog(
    products_api: ProductsApi,
    product_details_page: ProductDetailsPage,
) -> None:
    catalog = products_api.parse_products(products_api.get_products())
    product = next(item for item in catalog.products if item.id == 1)

    product_details_page.open_by_id(product.id)

    assert product.name.lower() in product_details_page.name().lower()
    assert product.price.replace(" ", "").lower() in product_details_page.price().replace(" ", "").lower()
