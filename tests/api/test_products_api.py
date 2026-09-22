import allure
import pytest

from ecom_taf.api import ProductsApi


@allure.epic("API")
@allure.feature("Products")
@allure.severity(allure.severity_level.CRITICAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /productsList")
@pytest.mark.api
@pytest.mark.smoke
def test_get_all_products_returns_catalog(products_api: ProductsApi) -> None:
    result = products_api.get_products()

    assert result.http_status == 200
    catalog = products_api.parse_products(result)
    assert catalog.response_code == 200
    assert len(catalog.products) > 0
    first = catalog.products[0]
    assert first.id > 0
    assert first.name
    assert first.price
    assert first.brand


@allure.epic("API")
@allure.feature("Products")
@allure.severity(allure.severity_level.MINOR)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /productsList")
@pytest.mark.api
@pytest.mark.negative
def test_post_products_is_not_supported(products_api: ProductsApi) -> None:
    result = products_api.post_products()

    assert result.response_code == 405
    assert "not supported" in (result.message or "").lower()


@allure.epic("API")
@allure.feature("Brands")
@allure.severity(allure.severity_level.NORMAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /brandsList")
@pytest.mark.api
def test_get_brands_list(products_api: ProductsApi) -> None:
    result = products_api.get_brands()

    assert result.http_status == 200
    assert result.response_code == 200
    assert result.payload.get("brands")


@allure.epic("API")
@allure.feature("Brands")
@allure.severity(allure.severity_level.MINOR)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /brandsList")
@pytest.mark.api
@pytest.mark.negative
def test_put_brands_is_not_supported(products_api: ProductsApi) -> None:
    result = products_api.put_brands()
    assert result.response_code == 405
