"""The storefront pages, rendered server-side with the markup the page objects select on.

Selectors are structural in the suite (`.productinfo p`, `.product-information
span span`, `.cart_quantity button`), so the templates reproduce that nesting,
not just the text. Adding to the cart is a plain request followed by a redirect
back to the page with `?added=<id>`: the "added to cart" modal is then part of
the rendered page, visible the moment the navigation lands, with no script and
no timing for a test to race against.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from stand.app import catalog
from stand.app.store import ACCOUNT_FIELDS, Session

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))

SESSION_COOKIE = "stand_session"


def session_of(request: Request) -> Session:
    """The session the middleware in main.py attached to this request."""
    return request.state.session


def current_account(request: Request) -> dict[str, str] | None:
    session = session_of(request)
    return request.app.state.accounts.get(session.email) if session.email else None


def _render(request: Request, template: str, **context) -> HTMLResponse:
    account = current_account(request)
    return templates.TemplateResponse(
        request,
        template,
        {"account": account, "logged_in_as": account["firstname"] if account else None, **context},
    )


def _cart_lines(session: Session) -> list[dict]:
    lines = []
    for product_id, quantity in session.cart.items():
        product = catalog.by_id(product_id)
        if product is not None:
            lines.append({**product, "quantity": quantity})
    return lines


async def _form(request: Request) -> dict[str, str]:
    return {key: str(value) for key, value in (await request.form()).items()}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _render(request, "home.html", products=catalog.PRODUCTS, added=None)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "login.html", login_error=None, signup_error=None)


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    form = await _form(request)
    email, password = form.get("email", ""), form.get("password", "")
    if not request.app.state.accounts.verify(email, password):
        return _render(request, "login.html", login_error="Your email or password is incorrect!", signup_error=None)
    session_of(request).email = email
    return RedirectResponse("/", status_code=303)


@router.post("/signup", response_class=HTMLResponse)
async def signup_start(request: Request):
    form = await _form(request)
    if request.app.state.accounts.get(form.get("email", "")) is not None:
        return _render(request, "login.html", login_error=None, signup_error="Email Address already exist!")
    session_of(request).pending_signup = {"name": form.get("name", ""), "email": form.get("email", "")}
    return RedirectResponse("/signup", status_code=303)


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    pending = session_of(request).pending_signup or {"name": "", "email": ""}
    return _render(
        request,
        "signup.html",
        pending=pending,
        days=[str(day) for day in range(1, 32)],
        months=[str(month) for month in range(1, 13)],
        years=[str(year) for year in range(1950, 2011)],
    )


@router.post("/signup/create", response_class=HTMLResponse)
async def signup_create(request: Request):
    form = await _form(request)
    pending = session_of(request).pending_signup or {}
    fields = {name: form.get(name, "") for name in ACCOUNT_FIELDS}
    fields["name"] = fields["name"] or pending.get("name", "")
    fields["email"] = fields["email"] or pending.get("email", "")
    fields["address1"] = fields["address1"] or form.get("address", "")
    fields["firstname"] = fields["firstname"] or form.get("first_name", "")
    fields["lastname"] = fields["lastname"] or form.get("last_name", "")
    request.app.state.accounts.create(fields)
    session_of(request).pending_signup = None
    session_of(request).email = fields["email"]
    return _render(request, "account_created.html")


@router.get("/products", response_class=HTMLResponse)
async def products(request: Request, search: str | None = None, added: int | None = None):
    listed = catalog.search(search) if search else catalog.PRODUCTS
    title = "Searched Products" if search else "All Products"
    return _render(
        request,
        "products.html",
        products=listed,
        title=title,
        added=catalog.by_id(added) if added else None,
    )


@router.get("/product_details/{product_id}", response_class=HTMLResponse)
async def product_details(request: Request, product_id: int, added: int | None = None):
    product = catalog.by_id(product_id)
    if product is None:
        return HTMLResponse("Product not found", status_code=404)
    return _render(request, "product_details.html", product=product, added=catalog.by_id(added) if added else None)


def _add(session: Session, product_id: int, quantity: int) -> None:
    if catalog.by_id(product_id) is not None and quantity > 0:
        session.cart[product_id] = session.cart.get(product_id, 0) + quantity


@router.get("/add_to_cart/{product_id}")
async def add_to_cart_link(request: Request, product_id: int):
    _add(session_of(request), product_id, 1)
    return RedirectResponse(f"/products?added={product_id}", status_code=303)


@router.post("/add_to_cart")
async def add_to_cart_form(request: Request):
    form = await _form(request)
    product_id = int(form.get("product_id", "0") or 0)
    quantity = int(form.get("quantity", "1") or 1)
    _add(session_of(request), product_id, quantity)
    return RedirectResponse(f"/product_details/{product_id}?added={product_id}", status_code=303)


@router.get("/view_cart", response_class=HTMLResponse)
async def view_cart(request: Request):
    return _render(request, "cart.html", lines=_cart_lines(session_of(request)))


@router.get("/checkout", response_class=HTMLResponse)
async def checkout(request: Request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    return _render(request, "checkout.html", lines=_cart_lines(session_of(request)))


@router.get("/payment", response_class=HTMLResponse)
async def payment(request: Request):
    if current_account(request) is None:
        return RedirectResponse("/login", status_code=303)
    return _render(request, "payment.html")


@router.post("/payment", response_class=HTMLResponse)
async def pay(request: Request):
    await _form(request)  # any card is accepted: the stand processes no payment
    session_of(request).cart.clear()
    return _render(request, "order_placed.html")


@router.get("/logout")
async def logout(request: Request):
    session_of(request).email = None
    return RedirectResponse("/login", status_code=303)
