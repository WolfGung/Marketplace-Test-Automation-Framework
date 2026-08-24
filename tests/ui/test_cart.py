import allure
import pytest

from ecom_taf.ui.pages import CartPage, ProductDetailsPage, ProductsPage


@allure.epic("UI")
@allure.feature("Cart")
@pytest.mark.ui
def test_add_product_from_catalog_to_cart(
    products_page: ProductsPage,
    cart_page: CartPage,
) -> None:
    products_page.open()
    first_name = products_page.product_names()[0]
    products_page.add_first_product_to_cart()
    products_page.view_cart_from_modal()

    cart_items = cart_page.product_names()
    assert any(first_name.lower() in item.lower() or item.lower() in first_name.lower() for item in cart_items)


@allure.epic("UI")
@allure.feature("Cart")
@pytest.mark.ui
def test_add_product_with_quantity_from_details(
    product_details_page: ProductDetailsPage,
    products_page: ProductsPage,
    cart_page: CartPage,
) -> None:
    product_details_page.open_by_id(2)
    name = product_details_page.name()
    product_details_page.add_to_cart(quantity=3)
    products_page.view_cart_from_modal()

    assert any(name.lower() in item.lower() for item in cart_page.product_names())
    assert "3" in " ".join(cart_page.quantities())
