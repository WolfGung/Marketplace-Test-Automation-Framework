from __future__ import annotations

from ecom_taf.api.client import ApiResult, HttpClient
from ecom_taf.models.product import ProductsResponse


class ProductsApi:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get_products(self) -> ApiResult:
        return self._http.request("GET", "/productsList")

    def post_products(self) -> ApiResult:
        return self._http.request("POST", "/productsList")

    def get_brands(self) -> ApiResult:
        return self._http.request("GET", "/brandsList")

    def put_brands(self) -> ApiResult:
        return self._http.request("PUT", "/brandsList")

    def search(self, query: str | None = None) -> ApiResult:
        data = {"search_product": query} if query is not None else None
        return self._http.request("POST", "/searchProduct", data=data)

    def parse_products(self, result: ApiResult) -> ProductsResponse:
        return ProductsResponse.model_validate(result.payload)
