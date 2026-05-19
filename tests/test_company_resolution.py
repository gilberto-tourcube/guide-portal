"""Tests for CompanyResolutionMiddleware (#160).

The middleware reads company_code/mode from the session and sets
``request.state.company`` to the resolved CompanyConfig or None.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.testclient import TestClient

from app.config import settings
from app.middleware.company_resolution import CompanyResolutionMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CompanyResolutionMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test")

    @app.get("/_probe")
    async def probe(request: Request):
        company = getattr(request.state, "company", "MISSING")
        return JSONResponse({
            "company_present": company is not None and company != "MISSING",
            "company_id": getattr(company, "company_id", None),
        })

    @app.get("/_setup")
    async def setup(request: Request, company_code: str, mode: str):
        request.session["company_code"] = company_code
        request.session["mode"] = mode
        return JSONResponse({"ok": True})

    return app


def test_anonymous_request_has_no_company():
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/_probe")
    assert resp.status_code == 200
    assert resp.json() == {"company_present": False, "company_id": None}


def test_resolved_session_populates_company():
    app = _build_app()
    client = TestClient(app)
    # Pick the first real tenant from apikey.json
    first_tenant = next(iter(settings._load_company_configs().keys()))
    client.get(f"/_setup?company_code={first_tenant}&mode=Test")
    resp = client.get("/_probe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_present"] is True
    assert body["company_id"] == first_tenant
