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


def _render(request: Request, template: str, *, status_code: int = 200, **context) -> HTMLResponse:
    """One page, with the account the header shows worked out for it.

    The header on the site this reproduces reads "Logged in as <the account's
    name>", not its first name: the name is what the registration form asks for
    first and what the site greets a customer by. An account created through
    the API may carry no name at all, in which case the first name is what
    there is, so that is the fallback rather than an empty greeting.
    """
    account = current_account(request)
    logged_in_as = (account["name"] or account["firstname"]) if account else None
    return templates.TemplateResponse(
        request,
        template,
        {"account": account, "logged_in_as": logged_in_as, **context},
        status_code=status_code,
    )


def _cart_lines(session: Session) -> list[dict]:
    lines = []
    for product_id, quantity in session.cart.items():
        product = catalog.by_id(product_id)
        if product is not None:
            lines.append({**product, "quantity": quantity})
    return lines


async def _form(request: Request) -> dict[str, str]:
    """This request's form fields, whatever content type they arrived in.

    Deliberately not `api._form`, which answers `{}` to anything that is not
    `application/x-www-form-urlencoded`. That refusal exists because the REST
    API reproduces a documented answer -- "parameter is missing in POST
    request", inside HTTP 200 -- and a door with no such answer has nothing to
    gain by rejecting a type. A browser posting one of these forms sends
    urlencoded; the forms here carry no file, so nothing makes one multipart;
    and Starlette hands back an empty form for a body it does not recognise
    rather than raising, so a hand-made request with the wrong header lands on
    the same page an empty form lands on -- "Your email or password is
    incorrect!" -- which is exactly what it deserves.
    """
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
    if not request.app.state.accounts.create(fields):
        # The store refuses a taken email and an empty one, and the page used
        # to say ACCOUNT CREATED! regardless -- then log the visitor in as the
        # holder of an account this request did not create. The second form on
        # the login page is where that email was entered, so the answer belongs
        # there, and it is the same sentence `/signup` gives for the same
        # reason. The half-finished signup is left in the session: the visitor
        # is one corrected field away from finishing it.
        return _render(
            request,
            "login.html",
            status_code=400,
            login_error=None,
            signup_error="Email Address already exist!",
        )
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


def _whole_number(raw: str, fallback: int) -> int | None:
    """`raw` as an integer, `fallback` when it is empty, None when it is neither.

    The quantity comes from a text input and the product id from a hidden
    field, so both arrive as whatever was posted. `int("two")` raises
    ValueError, which FastAPI has no answer for in a page route: the visitor
    gets a 500 and a traceback in the log for typing a word into a box. None
    here is the caller's cue to answer 400 instead.
    """
    raw = raw.strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return None


@router.post("/add_to_cart")
async def add_to_cart_form(request: Request):
    form = await _form(request)
    product_id = _whole_number(form.get("product_id", ""), 0)
    quantity = _whole_number(form.get("quantity", ""), 1)
    if product_id is None or quantity is None:
        return HTMLResponse("bad request", status_code=400)
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
