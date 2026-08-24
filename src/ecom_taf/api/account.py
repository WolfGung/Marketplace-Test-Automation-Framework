from __future__ import annotations

from ecom_taf.api.client import ApiResult, HttpClient
from ecom_taf.models.user import UserAccount


class AccountApi:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create_account(self, user: UserAccount) -> ApiResult:
        return self._http.request("POST", "/createAccount", data=user.to_api_form())

    def delete_account(self, email: str, password: str) -> ApiResult:
        return self._http.request(
            "DELETE",
            "/deleteAccount",
            data={"email": email, "password": password},
        )

    def update_account(self, user: UserAccount) -> ApiResult:
        return self._http.request("PUT", "/updateAccount", data=user.to_api_form())

    def get_user_by_email(self, email: str) -> ApiResult:
        return self._http.request("GET", "/getUserDetailByEmail", params={"email": email})

    def verify_login(self, email: str | None = None, password: str | None = None) -> ApiResult:
        data: dict[str, str] = {}
        if email is not None:
            data["email"] = email
        if password is not None:
            data["password"] = password
        return self._http.request("POST", "/verifyLogin", data=data or None)

    def delete_verify_login(self) -> ApiResult:
        return self._http.request("DELETE", "/verifyLogin")
