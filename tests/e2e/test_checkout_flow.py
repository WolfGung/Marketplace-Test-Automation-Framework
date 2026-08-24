import allure
import pytest

from ecom_taf.models.user import UserAccount
from ecom_taf.ui.pages import (
    AuthPage,
    CartPage,
    CheckoutPage,
    HomePage,
    PaymentPage,
    ProductDetailsPage,
    ProductsPage,
)


@allure.epic("E2E")
@allure.feature("Checkout")
@pytest.mark.e2e
@pytest.mark.smoke
def test_logged_in_user_can_place_an_order(
    registered_user: UserAccount,
    auth_page: AuthPage,
    home_page: HomePage,
    product_details_page: ProductDetailsPage,
    products_page: ProductsPage,
    cart_page: CartPage,
    checkout_page: CheckoutPage,
    payment_page: PaymentPage,
) -> None:
    auth_page.open()
    auth_page.login(registered_user.email, registered_user.password)
    home_page.logged_in_as().wait_for(state="visible")

    product_details_page.open_by_id(1)
    product_name = product_details_page.name()
    product_details_page.add_to_cart(quantity=1)
    products_page.view_cart_from_modal()

    assert any(product_name.lower() in item.lower() for item in cart_page.product_names())
    cart_page.proceed_to_checkout()

    assert registered_user.firstname.lower() in checkout_page.delivery_address().lower()
    checkout_page.place_order()

    payment_page.pay(name_on_card=registered_user.name)
    assert "order" in payment_page.order_placed_message().lower()
