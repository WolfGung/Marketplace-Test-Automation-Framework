"""The stand: a small shop with the same pages and REST API as the public demo site.

`create_app()` builds a fresh application with empty stores — one per test in
the contract tests, one per process when served with uvicorn. `app` is what
`uvicorn stand.app.main:app` and the compose service run.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from stand.app.api import router as api_router
from stand.app.pages import SESSION_COOKIE
from stand.app.pages import router as pages_router
from stand.app.store import AccountStore, SessionStore

#: Paths that are served without a session. The REST API is stateless -- every
#: call carries whatever credentials it needs in its own body -- and the static
#: files are files. Attaching a session to those was one entry in the session
#: store per request, kept for the life of the process, plus a `Set-Cookie` on
#: every JSON answer the API client was never going to send back. Only the
#: pages have a visitor to remember.
SESSIONLESS_PREFIXES = ("/api/", "/static/")


def create_app() -> FastAPI:
    app = FastAPI(title="Marketplace stand", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.accounts = AccountStore()
    app.state.sessions = SessionStore()

    @app.middleware("http")
    async def attach_session(request: Request, call_next):
        if request.url.path.startswith(SESSIONLESS_PREFIXES):
            return await call_next(request)
        token, session = app.state.sessions.get_or_create(request.cookies.get(SESSION_COOKIE))
        request.state.session = session
        response = await call_next(request)
        if request.cookies.get(SESSION_COOKIE) != token:
            response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
        return response

    app.mount("/static", StaticFiles(directory=str(Path(__file__).with_name("static"))), name="static")
    app.include_router(api_router)
    app.include_router(pages_router)
    return app


app = create_app()
