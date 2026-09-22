"""The REST API under /api, answering the way the public demo API does.

Every response is HTTP 200 and carries the real outcome in `responseCode`;
request bodies are form-encoded; messages are the public API's own. The suite's
API client parses exactly that shape, so the stand keeps it.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from stand.app import catalog

router = APIRouter(prefix="/api")

NOT_SUPPORTED = {"responseCode": 405, "message": "This request method is not supported."}
MISSING_SEARCH_PARAM = {
    "responseCode": 400,
    "message": "Bad request, search_product parameter is missing in POST request.",
}
MISSING_LOGIN_PARAMS = {
    "responseCode": 400,
    "message": "Bad request, email or password parameter is missing in POST request.",
}


def _answer(body: dict) -> JSONResponse:
    return JSONResponse(status_code=200, content=body)


async def _form(request: Request) -> dict[str, str]:
    if not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        return {}
    return {key: str(value) for key, value in (await request.form()).items()}


@router.get("/productsList")
async def products_list() -> JSONResponse:
    return _answer({"responseCode": 200, "products": catalog.PRODUCTS})


@router.post("/productsList")
async def products_list_post() -> JSONResponse:
    return _answer(NOT_SUPPORTED)


@router.get("/brandsList")
async def brands_list() -> JSONResponse:
    return _answer({"responseCode": 200, "brands": catalog.BRANDS})


@router.put("/brandsList")
async def brands_list_put() -> JSONResponse:
    return _answer(NOT_SUPPORTED)


@router.post("/searchProduct")
async def search_product(request: Request) -> JSONResponse:
    form = await _form(request)
    if "search_product" not in form:
        return _answer(MISSING_SEARCH_PARAM)
    return _answer({"responseCode": 200, "products": catalog.search(form["search_product"])})


@router.post("/createAccount")
async def create_account(request: Request) -> JSONResponse:
    form = await _form(request)
    if "email" not in form or "password" not in form:
        return _answer(MISSING_LOGIN_PARAMS)
    if not request.app.state.accounts.create(form):
        return _answer({"responseCode": 400, "message": "Email already exists!"})
    return _answer({"responseCode": 201, "message": "User created!"})


@router.delete("/deleteAccount")
async def delete_account(request: Request) -> JSONResponse:
    form = await _form(request)
    if request.app.state.accounts.delete(form.get("email", ""), form.get("password", "")):
        return _answer({"responseCode": 200, "message": "Account deleted!"})
    return _answer({"responseCode": 404, "message": "Account not found!"})


@router.put("/updateAccount")
async def update_account(request: Request) -> JSONResponse:
    form = await _form(request)
    if request.app.state.accounts.update(form):
        return _answer({"responseCode": 200, "message": "User updated!"})
    return _answer({"responseCode": 404, "message": "Account not found!"})


@router.get("/getUserDetailByEmail")
async def get_user_detail(request: Request, email: str = "") -> JSONResponse:
    account = request.app.state.accounts.get(email)
    if account is None:
        return _answer({"responseCode": 404, "message": "Account not found with this email, try another email!"})
    public = {key: value for key, value in account.items() if key != "password"}
    return _answer({"responseCode": 200, "user": public})


@router.post("/verifyLogin")
async def verify_login(request: Request) -> JSONResponse:
    form = await _form(request)
    if "email" not in form or "password" not in form:
        return _answer(MISSING_LOGIN_PARAMS)
    if request.app.state.accounts.verify(form["email"], form["password"]):
        return _answer({"responseCode": 200, "message": "User exists!"})
    return _answer({"responseCode": 404, "message": "User not found!"})


@router.delete("/verifyLogin")
async def verify_login_delete() -> JSONResponse:
    return _answer(NOT_SUPPORTED)
