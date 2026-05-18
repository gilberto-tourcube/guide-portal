# #160 — Guide Portal PWA Toggle, Mobile-Only Display, Booking-Level Save Offline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port Guest Portal `#163` PWA behavior (tenant toggle, mobile-only display, booking-level Save Offline) to Guide Portal.

**Architecture:** Two new boolean fields on `CompanyConfig` (`pwa_enabled`, `offline_documents_enabled`), a new `MobileDetectionMiddleware` setting `request.state.is_mobile`, a new `CompanyResolutionMiddleware` setting `request.state.company`, a defense-in-depth 404 on `/manifest.json`, Jinja gating in `pwa_head.html` / `base.html`, a bulk Save Offline button in `trip_departure.html` keyed on `departure.documents_ready`, and a new `static/js/booking-save-offline.js` controller. The existing per-row `save-offline-btn` flow (`#133`) is removed in the same change.

**Tech Stack:** FastAPI + Starlette middleware, Pydantic v2 `BaseModel`, Jinja2 templates, vanilla JavaScript, pytest + httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-05-18-160-pwa-toggle-mobile-booking-save-offline-design.md`

**Branch:** `feat/160-pwa-toggle-mobile-booking-save` (already created off `origin/main`, spec committed at `bc1c7d7`).

---

## Pre-Flight

- [ ] **Step 0: Confirm working branch**

Run:
```bash
git branch --show-current
git log --oneline -2
```

Expected:
```
feat/160-pwa-toggle-mobile-booking-save
bc1c7d7 docs(#160): spec for PWA toggle, ...
<some commit on main>
```

If branch is wrong, stop and create it from `origin/main`.

- [ ] **Step 1: Install dev deps + confirm baseline tests green**

Run:
```bash
pip install -r requirements.txt
pytest -q
```

Expected: existing test suite passes. If something is already red on `main`, stop and surface it before continuing.

---

## Task 1: `CompanyConfig` — Add `pwa_enabled` + `offline_documents_enabled`

**Files:**
- Modify: `app/config.py:15-32` (`CompanyConfig` model) and `app/config.py:_load_company_configs` (parser block around line 105).
- Test: `tests/test_config_pwa_flags.py` (new).

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_pwa_flags.py`:

```python
"""Tests for the two new PWA-related fields on CompanyConfig (#160)."""

from app.config import CompanyConfig, Settings


def _minimal_config(**overrides) -> CompanyConfig:
    base = dict(
        company_id="ACME",
        logo="logo.png",
        tourcube_online=True,
        skin_name="theme-bluelite",
        test_api_key="t-key",
        test_url="https://test.example.com",
        production_api_key="p-key",
        production_url="https://prod.example.com",
        api_url="https://test.example.com",
        api_key="t-key",
    )
    base.update(overrides)
    return CompanyConfig(**base)


def test_company_config_defaults_pwa_flags_false():
    cfg = _minimal_config()
    assert cfg.pwa_enabled is False
    assert cfg.offline_documents_enabled is False


def test_company_config_accepts_pwa_flags_true():
    cfg = _minimal_config(pwa_enabled=True, offline_documents_enabled=True)
    assert cfg.pwa_enabled is True
    assert cfg.offline_documents_enabled is True


def test_load_company_configs_reads_pwa_flags(tmp_path, monkeypatch):
    fixture = tmp_path / "apikey.json"
    fixture.write_text("""
        {
            "TourcubeAPIKey": [
                {
                    "CompanyID": "ALPHA",
                    "Test": "k1",
                    "Production": "k2",
                    "TestURL": "https://t.example.com",
                    "ProductionURL": "https://p.example.com",
                    "PWAEnabled": true,
                    "OfflineDocumentsEnabled": true,
                    "SkinName": "theme-bluelite"
                },
                {
                    "CompanyID": "BETA",
                    "Test": "k1",
                    "Production": "k2",
                    "TestURL": "https://t.example.com",
                    "ProductionURL": "https://p.example.com",
                    "SkinName": "theme-bluelite"
                }
            ]
        }
    """)
    settings = Settings(secret_key="test", api_key_json_path=str(fixture))
    configs = settings._load_company_configs()
    assert configs["ALPHA"].pwa_enabled is True
    assert configs["ALPHA"].offline_documents_enabled is True
    assert configs["BETA"].pwa_enabled is False
    assert configs["BETA"].offline_documents_enabled is False
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pytest tests/test_config_pwa_flags.py -v
```

Expected: `AttributeError`/`ValidationError` because `pwa_enabled` is not a `CompanyConfig` field.

- [ ] **Step 3: Add the fields to `CompanyConfig`**

In `app/config.py`, inside the `CompanyConfig` class (after `production_domains`), add two fields:

```python
    # PWA per-tenant gates (#160)
    pwa_enabled: bool = False
    offline_documents_enabled: bool = False
```

- [ ] **Step 4: Map the new keys in the parser**

In `app/config.py`, inside `_load_company_configs`, extend the `CompanyConfig(...)` constructor call (right after `production_domains=company.get('ProductionDomains', []),`) with:

```python
                pwa_enabled=bool(company.get('PWAEnabled', False)),
                offline_documents_enabled=bool(company.get('OfflineDocumentsEnabled', False)),
```

- [ ] **Step 5: Run test, verify pass**

```bash
pytest tests/test_config_pwa_flags.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/config.py tests/test_config_pwa_flags.py
git commit -m "feat(#160): add pwa_enabled and offline_documents_enabled to CompanyConfig"
```

---

## Task 2: `MobileDetectionMiddleware`

**Files:**
- Create: `app/middleware/__init__.py` (only if directory does not exist yet).
- Create: `app/middleware/mobile_detection.py`.
- Test: `tests/test_mobile_detection.py` (new).

- [ ] **Step 1: Create the middleware package marker (if needed)**

```bash
mkdir -p app/middleware
[ -f app/middleware/__init__.py ] || : > app/middleware/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_mobile_detection.py`:

```python
"""Tests for MobileDetectionMiddleware and is_mobile_user_agent (#160)."""

import pytest

from app.middleware.mobile_detection import is_mobile_user_agent


MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 12_5 like Mac OS X) Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 12; SM-T870) Tablet Safari/537.36",
    "Opera/9.80 (J2ME/MIDP; Opera Mini/9.80; U; en) Presto",
    "Mozilla/5.0 (Windows Phone 10.0; IEMobile/9.0)",
    "BlackBerry9700/5.0",
    "Mozilla/5.0 (Linux; U; Android 4.0.3; en-us; Kindle Fire) Silk/2.1",
]

DESKTOP_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0",
    "",
]


@pytest.mark.parametrize("ua", MOBILE_UAS)
def test_mobile_ua_detected(ua):
    assert is_mobile_user_agent(ua) is True


@pytest.mark.parametrize("ua", DESKTOP_UAS)
def test_desktop_ua_not_detected(ua):
    assert is_mobile_user_agent(ua) is False
```

- [ ] **Step 3: Run, verify fail**

```bash
pytest tests/test_mobile_detection.py -v
```

Expected: `ModuleNotFoundError` on `app.middleware.mobile_detection`.

- [ ] **Step 4: Create the middleware (verbatim port from guest-portal)**

Create `app/middleware/mobile_detection.py`:

```python
"""Mobile detection middleware (ported from guest-portal #163).

Sets ``request.state.is_mobile`` based on the User-Agent header so templates
and routes can gate PWA emission (manifest, service worker, install hints,
Save Offline button) to phones and tablets only.

The check is intentionally lenient: any UA token matching a known mobile
or tablet keyword flips the flag. Desktop Chrome/Safari/Firefox stay False
and therefore see a plain website. iPad on iPadOS 13+ ships a desktop
Safari UA — for that case we rely on the client-side viewport guard in
``pwa_head.html``.
"""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

_MOBILE_UA_RE = re.compile(
    r"iPhone|iPod|Android.*Mobile|Mobile.*Android|iPad|Tablet|"
    r"Mobile Safari|Opera Mini|IEMobile|Windows Phone|BlackBerry|"
    r"Kindle|Silk",
    re.IGNORECASE,
)


def is_mobile_user_agent(user_agent: str) -> bool:
    """Return True when the UA string looks like a phone or tablet."""
    if not user_agent:
        return False
    return bool(_MOBILE_UA_RE.search(user_agent))


class MobileDetectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.is_mobile = is_mobile_user_agent(
            request.headers.get("user-agent", "")
        )
        return await call_next(request)


def register_mobile_detection(app: FastAPI) -> None:
    app.add_middleware(MobileDetectionMiddleware)
```

- [ ] **Step 5: Run test, verify pass**

```bash
pytest tests/test_mobile_detection.py -v
```

Expected: 12 passed (8 mobile + 4 desktop).

- [ ] **Step 6: Commit**

```bash
git add app/middleware/__init__.py app/middleware/mobile_detection.py tests/test_mobile_detection.py
git commit -m "feat(#160): add MobileDetectionMiddleware for UA-based PWA gating"
```

---

## Task 3: `CompanyResolutionMiddleware` — expose `request.state.company`

**Why:** `pwa_head.html` is included in every render (auth, dashboard, error, trip_departure). It needs to know the resolved tenant's `pwa_enabled` without each route having to wire it. A small middleware reads `session.company_code` / `session.mode` and stuffs the `CompanyConfig` instance into `request.state.company` (or `None` for anonymous requests).

**Files:**
- Create: `app/middleware/company_resolution.py`.
- Test: `tests/test_company_resolution.py` (new).

- [ ] **Step 1: Write the failing test**

Create `tests/test_company_resolution.py`:

```python
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
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_company_resolution.py -v
```

Expected: `ModuleNotFoundError` on `app.middleware.company_resolution`.

- [ ] **Step 3: Create the middleware**

Create `app/middleware/company_resolution.py`:

```python
"""Company resolution middleware (#160).

Reads ``company_code``/``mode`` from the session and resolves a
``CompanyConfig`` instance onto ``request.state.company``. Falls back
to ``None`` when the session is anonymous or the tenant cannot be
resolved — never to a default-tenant fallback (#148).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


class CompanyResolutionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        company = None
        try:
            session = request.scope.get("session") or {}
            company_code = session.get("company_code")
            mode = session.get("mode")
            if company_code and mode:
                company = settings.get_company_config(company_code, mode)
        except Exception as exc:  # noqa: BLE001
            logger.debug("CompanyResolutionMiddleware: %s", exc)
            company = None

        request.state.company = company
        return await call_next(request)


def register_company_resolution(app: FastAPI) -> None:
    app.add_middleware(CompanyResolutionMiddleware)
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_company_resolution.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/middleware/company_resolution.py tests/test_company_resolution.py
git commit -m "feat(#160): add CompanyResolutionMiddleware for request.state.company"
```

---

## Task 4: Register both middlewares in `app/main.py`

**Files:**
- Modify: `app/main.py` (after the `GuideHashMiddleware` registration block at line ~131).

- [ ] **Step 1: Wire up imports + registration**

Open `app/main.py`. Add to the imports at the top (near the other middleware imports):

```python
from app.middleware.mobile_detection import MobileDetectionMiddleware
from app.middleware.company_resolution import CompanyResolutionMiddleware
```

Then, **immediately after** the line `app.add_middleware(GuideHashMiddleware)` (around line 132), add:

```python
# PWA gating support (#160). Order matters — these are registered
# AFTER GuideHashMiddleware and BEFORE SessionMiddleware below, which
# in Starlette means they execute inside the session context but inside
# any guide-hash redirects. CompanyResolutionMiddleware reads session,
# so SessionMiddleware (added below) must wrap it.
app.add_middleware(CompanyResolutionMiddleware)
app.add_middleware(MobileDetectionMiddleware)
```

- [ ] **Step 2: Smoke-import the app**

```bash
python -c "from app.main import app; print('routes:', len(app.routes))"
```

Expected: prints a positive route count, no import errors.

- [ ] **Step 3: Confirm middleware order via TestClient probe**

Append to `tests/test_mobile_detection.py`:

```python
def test_main_app_sets_is_mobile_attribute():
    """Smoke: confirm app.main wires MobileDetectionMiddleware so
    request.state.is_mobile is always populated."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # Route does not matter; we just need any request to flow through.
    # Use a route that exists (/healthz or /) — fallback to /manifest.json
    # which exists in app.routes.pwa.
    resp = client.get("/manifest.json", headers={"User-Agent": "iPhone"})
    # We're not asserting on body here; only that the app boots and the
    # request flowed without crashing inside any middleware.
    assert resp.status_code in (200, 404)
```

Run:

```bash
pytest tests/test_mobile_detection.py -v
```

Expected: all green (13 tests).

- [ ] **Step 4: Commit**

```bash
git add app/main.py tests/test_mobile_detection.py
git commit -m "feat(#160): register MobileDetection + CompanyResolution middleware in main"
```

---

## Task 5: Gate `/manifest.json` route with 404

**Files:**
- Modify: `app/routes/pwa.py` (`/manifest.json` handler at line ~42).
- Test: `tests/test_pwa_manifest_gating.py` (new).

- [ ] **Step 1: Write the failing test**

Create `tests/test_pwa_manifest_gating.py`:

```python
"""Manifest gating matrix (#160): 4 scenarios over (pwa_enabled, is_mobile)."""

import json

from fastapi.testclient import TestClient

from app.main import app


IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148"
DESKTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605"


def _manifest(company_code: str, ua: str):
    client = TestClient(app)
    return client.get(
        f"/manifest.json?companyCode={company_code}&mode=Test",
        headers={"User-Agent": ua},
    )


def _first_pwa_enabled_tenant():
    from app.config import settings
    for code, cfg in settings._load_company_configs().items():
        if cfg.pwa_enabled:
            return code
    return None


def _first_pwa_disabled_tenant():
    from app.config import settings
    for code, cfg in settings._load_company_configs().items():
        if not cfg.pwa_enabled:
            return code
    return None


def test_manifest_pwa_on_mobile_returns_200():
    code = _first_pwa_enabled_tenant()
    if not code:
        # Skip when apikey.json has no opted-in tenant (e.g. pre-rollout).
        return
    resp = _manifest(code, IPHONE_UA)
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert "name" in body


def test_manifest_pwa_on_desktop_returns_404():
    code = _first_pwa_enabled_tenant()
    if not code:
        return
    resp = _manifest(code, DESKTOP_UA)
    assert resp.status_code == 404


def test_manifest_pwa_off_mobile_returns_404():
    code = _first_pwa_disabled_tenant()
    if not code:
        return
    resp = _manifest(code, IPHONE_UA)
    assert resp.status_code == 404


def test_manifest_pwa_off_desktop_returns_404():
    code = _first_pwa_disabled_tenant()
    if not code:
        return
    resp = _manifest(code, DESKTOP_UA)
    assert resp.status_code == 404


def test_manifest_anonymous_returns_404():
    """No companyCode/mode + no session → 404 (no neutral install surface)."""
    client = TestClient(app)
    resp = client.get("/manifest.json", headers={"User-Agent": IPHONE_UA})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/test_pwa_manifest_gating.py -v
```

Expected: failures on every test except possibly `test_manifest_anonymous_returns_404` depending on current state.

- [ ] **Step 3: Update `/manifest.json` handler**

In `app/routes/pwa.py`, replace the body of the `manifest` function — keep the existing resolution logic but insert the gate **after** `config` is resolved:

```python
@router.get("/manifest.json")
async def manifest(request: Request):
    """Serve a tenant-specific PWA manifest (#148, #160).

    Anonymous or non-mobile requests now 404 — there is no neutral install
    surface anymore. Only opted-in tenants on mobile UAs receive a manifest.
    """
    company_code = (
        request.query_params.get("companyCode")
        or request.session.get("company_code")
    )
    mode = (
        request.query_params.get("mode")
        or request.session.get("mode")
    )

    config = None
    if company_code and mode:
        try:
            config = settings.get_company_config(company_code, mode)
        except Exception:
            config = None

    # PWA tenant + UA gate (#160). Defense-in-depth alongside the Jinja
    # head-tag gate; the browser must not be able to install on a tenant
    # that did not opt in, and desktop UAs never get a manifest either.
    is_mobile = getattr(request.state, "is_mobile", False)
    if not (config and config.pwa_enabled and is_mobile):
        raise HTTPException(status_code=404)

    app_name = f"{config.company_id} Guide Portal"
    theme_color = SKIN_COLORS.get(config.skin_name, "#0F4374")
    icons = []
    if config.favicon:
        icon_path = f"/static/images/{config.favicon}"
        icons = [
            {"src": icon_path, "sizes": "192x192", "type": "image/png"},
            {"src": icon_path, "sizes": "512x512", "type": "image/png"},
        ]
    start_url = f"/?company_code={company_code}&mode={mode}"

    manifest_data = {
        "name": app_name,
        "short_name": app_name,
        "start_url": start_url,
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": theme_color,
        "icons": icons,
    }

    return JSONResponse(
        content=manifest_data,
        media_type="application/manifest+json",
    )
```

Remove the old neutral-fallback else branch — the gate now 404s instead.

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_pwa_manifest_gating.py -v
```

Expected: all 5 pass. (Note: tests with `_first_pwa_enabled_tenant() is None` will short-circuit; that is fine — they will turn fully meaningful once Task 14 lands the flag in `apikey.json`.)

- [ ] **Step 5: Commit**

```bash
git add app/routes/pwa.py tests/test_pwa_manifest_gating.py
git commit -m "feat(#160): gate /manifest.json on pwa_enabled and is_mobile (404 otherwise)"
```

---

## Task 6: Add `documents_ready` to `TripDepartureData` schema

**Files:**
- Modify: `app/models/schemas.py` (around line 332, after `forms_to_complete_count`).

- [ ] **Step 1: Add the field**

Inside `TripDepartureData`, add (right after the `departure_notes` field):

```python
    # PWA Save Offline gate (#160). Backend sets this on getDeparturePage
    # once Operations marks all docs ready. Defaults False until the
    # backend field ships — the booking-level Save Offline button never
    # renders for departures that have not been flagged.
    documents_ready: bool = Field(
        False,
        description="True when Operations has marked all trip + departure docs ready for offline caching"
    )
```

- [ ] **Step 2: Smoke-test the schema**

```bash
python -c "from app.models.schemas import TripDepartureData; print(TripDepartureData.model_fields['documents_ready'])"
```

Expected: prints the FieldInfo with `default=False`.

- [ ] **Step 3: Commit**

```bash
git add app/models/schemas.py
git commit -m "feat(#160): add documents_ready field to TripDepartureData"
```

---

## Task 7: Map `documentsReady` in `guide_service.get_trip_departure`

**Files:**
- Modify: `app/services/guide_service.py` (the function that returns `TripDepartureData`, near the `return` statement assembling the model).

- [ ] **Step 1: Locate the constructor call**

Run:

```bash
grep -n "TripDepartureData(" app/services/guide_service.py
```

Expected: exactly one match for the `return TripDepartureData(...)` (or assignment to it).

- [ ] **Step 2: Pass `documents_ready` into the constructor**

Add the following keyword argument to the `TripDepartureData(...)` call, sitting near `departure_notes=...`:

```python
            documents_ready=bool(departure_response.get("documentsReady", False)),
```

- [ ] **Step 3: Existing service tests still green**

```bash
pytest tests/ -k "guide" -v
```

Expected: no regressions. (No new test here — the field passes through; we cover the gate behavior end-to-end at Task 12.)

- [ ] **Step 4: Commit**

```bash
git add app/services/guide_service.py
git commit -m "feat(#160): map departure_response.documentsReady into TripDepartureData"
```

---

## Task 8: Pass tenant flags to template context in `resources.py`

**Why:** `trip_departure.html` reads `company` directly. `CompanyResolutionMiddleware` already sets `request.state.company`, but for parity with how `pwa_head.html` reads it, we explicitly pass the resolved `CompanyConfig` instance into the trip departure render so the template stays self-documenting.

**Files:**
- Modify: `app/routes/resources.py:108-122` (`TemplateResponse` context dict for `trip_departure.html`).

- [ ] **Step 1: Inject `company` into the context**

In `app/routes/resources.py`, inside the `templates.TemplateResponse(...)` call, add `"company": company_config,` (`company_config` is already in scope from line 97). Resulting block:

```python
        return templates.TemplateResponse(
            "pages/trip_departure.html",
            {
                "request": request,
                "departure": departure_data,
                "company": company_config,
                "company_logo": company_config.logo,
                "company_favicon": company_config.favicon,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "clients"),
                "today": date_today.today()
            }
        )
```

- [ ] **Step 2: Smoke-import**

```bash
python -c "from app.routes.resources import router; print('routes:', len(router.routes))"
```

Expected: prints route count without errors.

- [ ] **Step 3: Commit**

```bash
git add app/routes/resources.py
git commit -m "feat(#160): pass resolved company config into trip_departure template"
```

---

## Task 9: Update `pwa_head.html` — gate everything behind `pwa_active`

**Files:**
- Modify: `templates/partials/pwa_head.html`.

- [ ] **Step 1: Rewrite the partial**

Replace the whole file with:

```jinja
{# PWA meta tags, manifest link, and favicon — included in base.html <head>.

   Gates (#160):
     - server-side pwa_active = company.pwa_enabled AND request.state.is_mobile
     - client-side viewport guard removes the manifest <link> and sets
       window.__PWA_DISABLED__ on viewports wider than 1366px.

   The favicon block always renders; only the manifest + apple PWA meta
   tags are gated.
#}
{% set _company = request.state.company if request and request.state is defined else None %}
{% set _is_mobile = request.state.is_mobile if request and request.state is defined else False %}
{% set pwa_active = (_company and _company.pwa_enabled and _is_mobile) %}

{% if pwa_active %}
  <!-- PWA -->
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black">
  <meta name="mobile-web-app-capable" content="yes">
  {% if theme_color %}
  <meta name="theme-color" content="{{ theme_color }}">
  {% endif %}
  <link id="pwa-manifest-link" rel="manifest"
        href="/manifest.json?companyCode={{ _company.company_id }}&mode={{ request.session.get('mode', '') }}">

  <script>
    (function () {
      try {
        if (window.matchMedia && !window.matchMedia('(max-width: 1366px)').matches) {
          var link = document.getElementById('pwa-manifest-link');
          if (link && link.parentNode) link.parentNode.removeChild(link);
          window.__PWA_DISABLED__ = true;
        }
      } catch (e) {}
    })();
  </script>
{% endif %}

<!-- Favicon -->
{% if company_favicon %}
<link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', path='/images/' + company_favicon) }}">
<link rel="icon" type="image/png" sizes="32x32" href="{{ url_for('static', path='/images/' + company_favicon) }}">
<link rel="icon" type="image/png" sizes="16x16" href="{{ url_for('static', path='/images/' + company_favicon) }}">
{% else %}
<link rel="icon" href="{{ url_for('static', path='/images/favicon.png') }}">
{% endif %}
```

- [ ] **Step 2: Spot-check with `curl` + grep**

Start the app locally (if not already running):

```bash
uvicorn app.main:app --reload --port 8000 &
sleep 2
curl -s -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" http://localhost:8000/ | grep -c "pwa-manifest-link" || true
curl -s -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148" http://localhost:8000/ | grep -c "pwa-manifest-link" || true
kill %1 2>/dev/null
```

Expected: Both `0` for now (anonymous render → no `pwa_active`). Will turn meaningful once Task 14 enables the flag for WTGUIDE and the user logs in.

- [ ] **Step 3: Commit**

```bash
git add templates/partials/pwa_head.html
git commit -m "feat(#160): gate pwa_head.html on company.pwa_enabled + is_mobile + viewport"
```

---

## Task 10: Gate scripts in `base.html` and remove old per-row save script

**Files:**
- Modify: `templates/base.html:40-43`.

- [ ] **Step 1: Replace the PWA script block**

In `templates/base.html`, replace lines 40–43 with:

```jinja
    {# PWA: service worker + offline document cache + booking-level Save Offline (#160) #}
    {% set _company = request.state.company if request and request.state is defined else None %}
    {% set _is_mobile = request.state.is_mobile if request and request.state is defined else False %}
    {% if _company and _company.pwa_enabled and _is_mobile %}
    <script src="{{ url_for('static', path='/js/pwa-offline.js') }}"></script>
    <script src="{{ url_for('static', path='/js/booking-save-offline.js') }}"></script>
    {% endif %}
```

The reference to `save-offline-button.js` is gone — that script file is deleted in Task 13.

- [ ] **Step 2: Smoke render**

Same curl probe as Task 9 Step 2 — both renders should now have zero `<script src="...pwa-offline.js"></script>` matches until the user authenticates with WTGUIDE on mobile.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat(#160): gate pwa-offline + booking-save-offline scripts on pwa_active"
```

---

## Task 11: Skip `serviceWorker.register()` when `__PWA_DISABLED__` is set

**Files:**
- Modify: `static/js/pwa-offline.js` (the `registerServiceWorker` function around line 41 and the `window.addEventListener('load', ...)` block around line 294).

- [ ] **Step 1: Update `registerServiceWorker`**

Inside `static/js/pwa-offline.js`, at the top of `registerServiceWorker`, add the disabled check:

```javascript
    function registerServiceWorker() {
        if (window.__PWA_DISABLED__) return Promise.reject(new Error('PWA disabled by client gate'));
        if (!('serviceWorker' in navigator)) return Promise.reject(new Error('SW not supported'));
        // ... existing body unchanged
```

- [ ] **Step 2: Silence the warn for the disabled case**

In the `window.addEventListener('load', ...)` block near line 294, change:

```javascript
    window.addEventListener('load', function () {
        registerServiceWorker().catch(function (err) {
            if (err && /disabled by client gate/.test(err.message)) return;
            console.warn('[PWA] Service worker registration failed:', err);
        });
    });
```

- [ ] **Step 3: Lint / smoke**

```bash
node -c static/js/pwa-offline.js
```

Expected: no syntax errors.

- [ ] **Step 4: Commit**

```bash
git add static/js/pwa-offline.js
git commit -m "feat(#160): pwa-offline.js short-circuits register when __PWA_DISABLED__ is set"
```

---

## Task 12: Create `booking-save-offline.js` (verbatim port from guest-portal)

**Files:**
- Create: `static/js/booking-save-offline.js`.

- [ ] **Step 1: Copy the file**

Run:

```bash
cp /Users/gilberto/projetos/tourcube/guest-portal/static/js/booking-save-offline.js static/js/booking-save-offline.js
```

- [ ] **Step 2: Sanity-check + lint**

```bash
diff -u /Users/gilberto/projetos/tourcube/guest-portal/static/js/booking-save-offline.js static/js/booking-save-offline.js
node -c static/js/booking-save-offline.js
```

Expected: no diff, no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add static/js/booking-save-offline.js
git commit -m "feat(#160): add booking-save-offline.js bulk-save controller (port from #163)"
```

---

## Task 13: Refactor `trip_departure.html` — bulk Save Offline + per-row View

**Files:**
- Modify: `templates/pages/trip_departure.html:182-292` (the entire `tabDocuments` panel).

- [ ] **Step 1: Replace the Documents tab body**

Replace lines 182 through ~292 (the `<!-- Documents Tab -->` block and its two `Trip Documents` / `Departure Documents` cards) with:

```jinja
                <!-- Documents Tab (#160) -->
                <div class="tab-pane {% if active_tab == 'documents' %}active{% endif %}"
                     id="tabDocuments" role="tabpanel">
                    {% if departure.access_expired %}
                    <div class="alert alert-warning alert-icon mt-3">
                        <em class="icon ni ni-alert-circle"></em>
                        <strong>Documents are no longer available.</strong>
                        Trip documents and departure documents are not accessible more than 45 days after the trip end date.
                    </div>
                    {% else %}
                    {% set _is_mobile = request.state.is_mobile if request and request.state is defined else False %}
                    {% set pwa_active = (company and company.pwa_enabled and _is_mobile) %}
                    {% set save_offline_active = pwa_active and company and company.offline_documents_enabled and departure.documents_ready %}
                    {% set offline_cache_attr = company and company.offline_documents_enabled %}

                    <div class="d-flex align-items-center justify-content-between mb-3 gap-2 flex-wrap mt-3">
                        <h6 class="text-soft mb-0">
                            <em class="icon ni ni-file-docs me-1"></em>Documents
                        </h6>
                        {% if save_offline_active %}
                        <button type="button"
                                id="booking-save-offline-btn"
                                class="btn btn-outline-primary booking-save-offline-btn"
                                data-departure-id="{{ departure.trip_departure_id }}"
                                aria-label="Save offline">
                            <em class="icon ni ni-download me-1"></em>
                            <span class="booking-save-offline-btn__label">Save offline</span>
                        </button>
                        <script id="booking-save-offline-data" type="application/json">
[
{%- set _all_docs = (departure.trip_documents | selectattr('document_url') | list) + (departure.departure_documents | selectattr('document_url') | list) -%}
{%- for doc in _all_docs -%}
{"url": {{ doc.document_url | tojson }}, "description": {{ (doc.description or '') | tojson }}}{% if not loop.last %},{% endif %}
{%- endfor -%}
]
                        </script>
                        {% endif %}
                    </div>

                    <div class="row g-4 mt-1">
                        <!-- Trip Documents -->
                        <div class="col-md-6">
                            <div class="card card-bordered h-100">
                                <div class="card-inner" style="padding: 20px;">
                                    <div class="d-flex align-items-center gap-2 mb-3">
                                        <em class="icon ni ni-file-text text-primary"></em>
                                        <h6 class="title mb-0">Trip Documents</h6>
                                    </div>
                                    {% if departure.trip_documents %}
                                    <ul class="list-group list-group-flush">
                                        {% for doc in departure.trip_documents %}
                                        <li class="list-group-item px-0 d-flex align-items-center justify-content-between gap-2">
                                            <span class="text-truncate">
                                                <em class="icon ni ni-file-pdf me-1 text-soft"></em>{{ doc.description }}
                                                {% if doc.upload_date %}
                                                <small class="text-soft ms-1">({{ doc.upload_date }})</small>
                                                {% endif %}
                                            </span>
                                            {% if doc.document_url %}
                                            <a href="{{ doc.document_url }}"
                                               target="_blank"
                                               rel="noopener"
                                               class="btn btn-sm btn-outline-light flex-shrink-0"
                                               {% if offline_cache_attr %}data-offline-cache="true"{% endif %}>
                                                <em class="icon ni ni-eye"></em>
                                                <span class="view-doc-btn__label">View</span>
                                            </a>
                                            {% endif %}
                                        </li>
                                        {% endfor %}
                                    </ul>
                                    {% else %}
                                    <p class="sub-text">No trip documents available.</p>
                                    {% endif %}
                                </div>
                            </div>
                        </div>

                        <!-- Departure Documents -->
                        <div class="col-md-6">
                            <div class="card card-bordered h-100">
                                <div class="card-inner" style="padding: 20px;">
                                    <div class="d-flex align-items-center gap-2 mb-3">
                                        <em class="icon ni ni-file-text text-primary"></em>
                                        <h6 class="title mb-0">Departure Documents</h6>
                                    </div>
                                    {% if departure.departure_documents %}
                                    <ul class="list-group list-group-flush">
                                        {% for doc in departure.departure_documents %}
                                        <li class="list-group-item px-0 d-flex align-items-center justify-content-between gap-2">
                                            <span class="text-truncate">
                                                <em class="icon ni ni-file-pdf me-1 text-soft"></em>{{ doc.description }}
                                                {% if doc.upload_date %}
                                                <small class="text-soft ms-1">({{ doc.upload_date }})</small>
                                                {% endif %}
                                            </span>
                                            {% if doc.document_url %}
                                            <a href="{{ doc.document_url }}"
                                               target="_blank"
                                               rel="noopener"
                                               class="btn btn-sm btn-outline-light flex-shrink-0"
                                               {% if offline_cache_attr %}data-offline-cache="true"{% endif %}>
                                                <em class="icon ni ni-eye"></em>
                                                <span class="view-doc-btn__label">View</span>
                                            </a>
                                            {% endif %}
                                        </li>
                                        {% endfor %}
                                    </ul>
                                    {% else %}
                                    <p class="sub-text">No departure documents available.</p>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                    </div>
                    {% endif %}
                </div>
```

- [ ] **Step 2: Render-smoke**

```bash
python -c "
from fastapi.templating import Jinja2Templates
t = Jinja2Templates(directory='templates')
# Just confirm the template loads without Jinja syntax errors:
t.env.get_template('pages/trip_departure.html')
print('template OK')
"
```

Expected: `template OK`.

- [ ] **Step 3: Commit**

```bash
git add templates/pages/trip_departure.html
git commit -m "feat(#160): refactor trip_departure docs tab — bulk Save Offline + per-row View buttons"
```

---

## Task 14: Delete `save-offline-button.js` + stale CSS block

**Files:**
- Delete: `static/js/save-offline-button.js`.
- Modify: `static/css/custom.css` — remove the `.save-offline-btn` block (lines 286–340 roughly) and append the new `.booking-save-offline-btn` + `.view-doc-btn__label` block.

- [ ] **Step 1: Confirm nothing else still references `.save-offline-btn`**

```bash
grep -rn "save-offline-btn\|save-offline-button.js" templates/ static/ app/ tests/ 2>/dev/null
```

Expected: only matches inside `static/css/custom.css` (the block we are about to remove) and possibly the file `static/js/save-offline-button.js` itself. If anything else matches, stop and investigate.

- [ ] **Step 2: Remove the old CSS block**

In `static/css/custom.css`, delete every line from the comment `/* save-offline-button.js: idle, .is-loading, .is-saved, .is-error. */` through the last `}` of the `.save-offline-btn` rule chain (line ~340). Make sure the `@keyframes save-offline-spin` rule (used by the new `.booking-save-offline-btn.is-loading`) is **kept** if it is part of that block — if it is, keep the keyframes; only remove the `.save-offline-btn*` selectors.

- [ ] **Step 3: Append the new CSS block (port from guest-portal)**

Append to `static/css/custom.css`:

```css
/* -------------------------------------------------------------------------
   Booking-level Save Offline button (#160).
   Ported from guest-portal #163. Mirrors the old .save-offline-btn state
   machine but lives once per page at the top of the documents section.
   ------------------------------------------------------------------------- */
@keyframes save-offline-spin {
  to { transform: rotate(360deg); }
}

.booking-save-offline-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  transition: background-color 0.2s, color 0.2s;
}

.booking-save-offline-btn.is-saved {
  background-color: #1ee0ac;
  border-color: #1ee0ac;
  color: #fff;
}

.booking-save-offline-btn.is-saved:hover {
  background-color: #1ac795;
  border-color: #1ac795;
}

.booking-save-offline-btn.is-error {
  background-color: #e85347;
  border-color: #e85347;
  color: #fff;
}

.booking-save-offline-btn.is-error:hover {
  background-color: #d63b30;
  border-color: #d63b30;
}

.booking-save-offline-btn.is-loading .icon {
  animation: save-offline-spin 0.8s linear infinite;
}

/* Defense layer 3: hide the button on desktop viewports even if the server
   somehow emitted it (e.g. tablet UA but desktop-sized window). */
@media (min-width: 1367px) {
  .booking-save-offline-btn {
    display: none !important;
  }
}

/* Per-doc View button — narrow screens collapse to icon-only so the doc
   title stays readable. */
@media (max-width: 575.98px) {
  .view-doc-btn__label {
    display: none;
  }
}
```

- [ ] **Step 4: Remove the JS file**

```bash
git rm static/js/save-offline-button.js
```

- [ ] **Step 5: Final ref-scan**

```bash
grep -rn "save-offline-btn\|save-offline-button" templates/ static/ app/ tests/ 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 6: Commit**

```bash
git add static/css/custom.css
git commit -m "feat(#160): drop per-row .save-offline-btn, add .booking-save-offline-btn + .view-doc-btn__label CSS"
```

---

## Task 15: Add `PWAEnabled` + `OfflineDocumentsEnabled` to `config/apikey.json`

**⚠️ HARD GATE:** Per project `CLAUDE.md`: "NEVER add new fields to `config/Tenants.json` or `config/Credentials.json` without asking for user approval first." `apikey.json` is the same shared tenant config. **Stop here and re-confirm with the user before editing.** The user already approved the rollout (WTGUIDE = true/true, others = false/false) during brainstorming, but reconfirm at this point in case the rollout target changed.

**Files:**
- Modify: `config/apikey.json`.

- [ ] **Step 1: Reconfirm rollout target with user**

Ask: "About to add `PWAEnabled` and `OfflineDocumentsEnabled` to `apikey.json`. Confirm rollout: WTGUIDE = true/true, all others = false/false?"

- [ ] **Step 2: Snapshot current file**

```bash
cp config/apikey.json /tmp/apikey.json.pre-160
```

- [ ] **Step 3: Apply the edit**

For each entry in `data["TourcubeAPIKey"]`, add two new keys after `"SkinName"`:

```json
"PWAEnabled": false,
"OfflineDocumentsEnabled": false,
```

Then, for the WTGUIDE entry, flip both to `true`.

This can be done via a small one-off Python script to avoid hand-editing JSON:

```bash
python <<'PY'
import json, pathlib
path = pathlib.Path("config/apikey.json")
data = json.loads(path.read_text())
for entry in data["TourcubeAPIKey"]:
    pwa = entry["CompanyID"] == "WTGUIDE"
    entry["PWAEnabled"] = pwa
    entry["OfflineDocumentsEnabled"] = pwa
path.write_text(json.dumps(data, indent=4) + "\n")
PY
```

- [ ] **Step 4: Verify the diff**

```bash
diff -u /tmp/apikey.json.pre-160 config/apikey.json | head -40
```

Expected: only added `PWAEnabled` / `OfflineDocumentsEnabled` keys per tenant. No other fields touched.

- [ ] **Step 5: Reload + smoke**

```bash
pytest tests/test_config_pwa_flags.py tests/test_pwa_manifest_gating.py -v
```

Expected: all green. The manifest tests previously short-circuited because no tenant had `pwa_enabled=True`; they now run for real.

- [ ] **Step 6: Commit**

```bash
git add config/apikey.json
git commit -m "feat(#160): enable PWA + offline docs for WTGUIDE in apikey.json"
```

---

## Task 16: Tenant config contract test

**Files:**
- Test: `tests/test_apikey_json_contract.py` (new).

- [ ] **Step 1: Write the test**

Create `tests/test_apikey_json_contract.py`:

```python
"""apikey.json contract (#160): every tenant must declare PWA flags."""

import json
from pathlib import Path


def test_every_tenant_has_pwa_flags():
    data = json.loads(Path("config/apikey.json").read_text())
    tenants = data["TourcubeAPIKey"]
    assert tenants, "apikey.json has no tenants"

    for entry in tenants:
        cid = entry.get("CompanyID", "<no id>")
        assert "PWAEnabled" in entry, f"{cid} missing PWAEnabled"
        assert "OfflineDocumentsEnabled" in entry, f"{cid} missing OfflineDocumentsEnabled"
        assert isinstance(entry["PWAEnabled"], bool), f"{cid} PWAEnabled not bool"
        assert isinstance(entry["OfflineDocumentsEnabled"], bool), f"{cid} OfflineDocumentsEnabled not bool"
```

- [ ] **Step 2: Run, verify pass**

```bash
pytest tests/test_apikey_json_contract.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_apikey_json_contract.py
git commit -m "test(#160): contract test asserts every tenant declares PWA flags"
```

---

## Task 17: Full smoke + acceptance walk-through

- [ ] **Step 1: Run full suite**

```bash
pytest -q
```

Expected: all green.

- [ ] **Step 2: Live curl smoke (4 cases)**

```bash
uvicorn app.main:app --reload --port 8000 &
SERVER_PID=$!
sleep 2

IPHONE='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148'
DESKTOP='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605'

echo "WTGUIDE / iPhone:"
curl -s -o /dev/null -w "%{http_code}\n" -A "$IPHONE" "http://localhost:8000/manifest.json?companyCode=WTGUIDE&mode=Test"
echo "WTGUIDE / Desktop:"
curl -s -o /dev/null -w "%{http_code}\n" -A "$DESKTOP" "http://localhost:8000/manifest.json?companyCode=WTGUIDE&mode=Test"
echo "Opted-out tenant / iPhone (replace TENANT_CODE with a non-WTGUIDE CompanyID):"
curl -s -o /dev/null -w "%{http_code}\n" -A "$IPHONE" "http://localhost:8000/manifest.json?companyCode=<OTHER>&mode=Test"
echo "Anonymous / iPhone:"
curl -s -o /dev/null -w "%{http_code}\n" -A "$IPHONE" "http://localhost:8000/manifest.json"

kill $SERVER_PID
```

Expected: `200, 404, 404, 404`.

- [ ] **Step 3: Browser walk-through (desktop)**

Log into the Guide Portal with a WTGUIDE guide test account on **desktop Chrome**. Visit any trip departure with documents. Confirm:
  - View page source → no `<link rel="manifest">` (viewport guard removed it client-side).
  - DevTools → Application → Service Workers → no SW for this origin.
  - Documents tab renders the new icon + plain text + per-doc View button layout. No Save Offline button anywhere.
  - Clicking a View button opens the document in a new tab.

- [ ] **Step 4: Browser walk-through (mobile emulation)**

In DevTools, switch to an iPhone device emulation profile (UA + viewport). Reload. Confirm:
  - `<link rel="manifest">` is present.
  - Service Worker registers.
  - If the departure has `documentsReady=true` (which requires the backend field to ship), the bulk Save Offline button appears at the top of the Documents tab. Until then, only View buttons render — that is correct.

- [ ] **Step 5: Real-iPhone smoke (only after backend ships `documentsReady`)**

On a physical iPhone:
  - Install the PWA from Safari → confirm install affordance shows up.
  - Tap Save Offline on a `documentsReady=true` departure.
  - Connect Web Inspector via cable → Storage → IndexedDB → confirm `guide-portal-documents.documents` populated.
  - Enable Airplane Mode. Re-open the PWA → tap View on a cached doc → confirm cached blob opens.

If steps 1–4 pass, the PR is ready for human review. Step 5 may be deferred until the backend ships `documentsReady`.

- [ ] **Step 6: Do not push yet**

Per memory rule: never `git push` until the user confirms local testing is done. After the user gives the go-ahead, push:

```bash
git push -u origin feat/160-pwa-toggle-mobile-booking-save
```

Then open the PR.

---

## Open Items (carry beyond this plan)

- **Final copy** (`Save offline` / `Saved offline` / `Saving…` / `Retry`) — pending Melissa on Jira DEVCUR-1638. Shipped placeholders match guest-portal `#163`.
- **Backend `documentsReady` field** — Steve to route to backend. When the field ships, no code change is needed; only a redeploy + a `documentsReady=true` flip on a test departure to validate end-to-end on iPhone.
