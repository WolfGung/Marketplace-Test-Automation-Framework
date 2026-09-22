"""The stand: a small shop with the same pages and REST API as the public demo site.

`create_app()` builds a fresh application with empty stores — one per test in
the contract tests, one per process when served with uvicorn. `app` is what
`uvicorn stand.app.main:app` and the compose service run.
"""
from __future__ import annotations

from fastapi import FastAPI

from stand.app.api import router as api_router
from stand.app.store import AccountStore, SessionStore


def create_app() -> FastAPI:
    app = FastAPI(title="Marketplace stand", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.accounts = AccountStore()
    app.state.sessions = SessionStore()
    app.include_router(api_router)
    return app


app = create_app()
