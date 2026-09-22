import allure
import pytest

from ecom_taf.ui.pages import HomePage


@allure.epic("UI")
@allure.feature("Home")
@allure.severity(allure.severity_level.CRITICAL)
@allure.link("https://www.automationexercise.com/", name="Page under test: the storefront home page")
@pytest.mark.ui
@pytest.mark.smoke
def test_home_page_loads(home_page: HomePage) -> None:
    home_page.open()
    assert home_page.is_loaded()
    assert "/login" in home_page.page.content() or home_page.page.locator("a[href='/login']").count() > 0
