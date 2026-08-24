from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import allure
import httpx

from ecom_taf.config import get_settings


@dataclass
class ApiResult:
    """Normalized API result.

    Automation Exercise often returns HTTP 200 while putting the real
    business status into the JSON `responseCode` field.
    """

    http_status: int
    response_code: int | None
    message: str | None
    payload: dict[str, Any]
    raw: httpx.Response

    def json_path(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


class HttpClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self._client = httpx.Client(
            base_url=base_url or settings.api_base_url,
            timeout=timeout or settings.http_timeout_s,
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> ApiResult:
        with allure.step(f"API {method.upper()} {path}"):
            if params:
                allure.attach(json.dumps(params, indent=2), "query", allure.attachment_type.JSON)
            if data:
                allure.attach(json.dumps(data, indent=2), "form", allure.attachment_type.JSON)
            if json_body:
                allure.attach(json.dumps(json_body, indent=2), "json", allure.attachment_type.JSON)

            response = self._client.request(
                method,
                path,
                params=params,
                data=data,
                json=json_body,
            )
            payload = _parse_payload(response)
            result = ApiResult(
                http_status=response.status_code,
                response_code=_as_int(payload.get("responseCode")),
                message=payload.get("message"),
                payload=payload,
                raw=response,
            )
            allure.attach(
                json.dumps(payload, indent=2, default=str),
                "response",
                allure.attachment_type.JSON,
            )
            return result


def _parse_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except json.JSONDecodeError:
        text = response.text.strip()
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    if isinstance(body, dict):
        return body
    return {"data": body}


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
