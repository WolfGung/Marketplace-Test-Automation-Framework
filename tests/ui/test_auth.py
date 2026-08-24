import allure
import pytest

from ecom_taf.models.user import UserAccount
from ecom_taf.ui.pages import AuthPage, HomePage


@allure.epic("UI")
@allure.feature("Authentication")
@pytest.mark.ui
@pytest.mark.smoke
def test_login_with_api_created_user(
    registered_user: UserAccount,
    auth_page: AuthPage,
    home_page: HomePage,
) -> None:
    auth_page.open()
    auth_page.login(registered_user.email, registered_user.password)
    home_page.logged_in_as().wait_for(state="visible")
    assert registered_user.name.split()[0] in home_page.logged_in_as().inner_text()


@allure.epic("UI")
@allure.feature("Authentication")
@pytest.mark.ui
@pytest.mark.negative
def test_login_with_invalid_password(auth_page: AuthPage) -> None:
    auth_page.open()
    auth_page.login("unknown.user@example.com", "invalid")
    assert "incorrect" in auth_page.login_error().lower()
