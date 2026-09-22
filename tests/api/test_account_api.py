import allure
import pytest

from ecom_taf.api import AccountApi
from ecom_taf.data import UserFactory
from ecom_taf.models.user import UserAccount


@allure.epic("API")
@allure.feature("Account")
@allure.severity(allure.severity_level.CRITICAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /createAccount")
@pytest.mark.api
@pytest.mark.smoke
@pytest.mark.destructive
def test_create_get_and_delete_user_account(account_api: AccountApi) -> None:
    user = UserFactory.build()
    created = account_api.create_account(user)
    assert created.response_code == 201

    details = account_api.get_user_by_email(user.email)
    assert details.response_code == 200
    user_payload = details.payload.get("user") or details.payload
    assert user.email in str(user_payload)

    deleted = account_api.delete_account(user.email, user.password)
    assert deleted.response_code == 200


@allure.epic("API")
@allure.feature("Account")
@allure.severity(allure.severity_level.NORMAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /updateAccount")
@pytest.mark.api
@pytest.mark.destructive
def test_update_user_account(registered_user: UserAccount, account_api: AccountApi) -> None:
    registered_user.company = "Updated QA Company"
    updated = account_api.update_account(registered_user)
    assert updated.response_code == 200


@allure.epic("API")
@allure.feature("Login")
@allure.severity(allure.severity_level.NORMAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /verifyLogin")
@pytest.mark.api
@pytest.mark.destructive
def test_verify_login_with_valid_user(registered_user: UserAccount, account_api: AccountApi) -> None:
    result = account_api.verify_login(registered_user.email, registered_user.password)
    assert result.response_code == 200
    assert "exist" in (result.message or "").lower()


@allure.epic("API")
@allure.feature("Login")
@allure.severity(allure.severity_level.MINOR)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /verifyLogin")
@pytest.mark.api
@pytest.mark.negative
def test_verify_login_without_email(account_api: AccountApi) -> None:
    result = account_api.verify_login(password="secret")
    assert result.response_code == 400


@allure.epic("API")
@allure.feature("Login")
@allure.severity(allure.severity_level.CRITICAL)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /verifyLogin")
@pytest.mark.api
@pytest.mark.negative
def test_verify_login_with_invalid_credentials(account_api: AccountApi) -> None:
    result = account_api.verify_login("missing.user@example.com", "wrong-password")
    assert result.response_code == 404


@allure.epic("API")
@allure.feature("Login")
@allure.severity(allure.severity_level.MINOR)
@allure.link("https://www.automationexercise.com/api_list", name="API under test: /verifyLogin")
@pytest.mark.api
@pytest.mark.negative
def test_delete_verify_login_not_supported(account_api: AccountApi) -> None:
    result = account_api.delete_verify_login()
    assert result.response_code == 405
