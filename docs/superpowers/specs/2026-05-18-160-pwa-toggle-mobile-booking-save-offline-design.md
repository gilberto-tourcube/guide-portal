# Spec — #160 Guide Portal PWA Toggle, Mobile-Only Display, and Booking-Level Save Offline

**Created:** 2026-05-18
**Backlog ticket:** `TOURCUBE/Backlog/160 - Guide Portal - PWA Toggle, Mobile-Only Display, and Booking-Level Save Offline`
**Source spec (upstream):** Jira DEVCUR-1638 (Steven Erts) — Guest & Guide Portal PWA
**Reference implementation:** `guest-portal` PRs #181 (`3d8bd0e`) + #182 (`8bda6d1`) covering ticket #163
**Target branch:** `feat/160-pwa-toggle-mobile-booking-save` (off `origin/main`)
**Target version:** Guide Portal 7.0x

---

## 1. Goal

Port the three PWA behavior changes shipped in the Guest Portal (`#163`) to the Guide Portal, preserving the same observable behavior for opted-in tenants. After this change:

1. PWA install / service-worker / Save Offline UI is a **per-tenant** opt-in (no longer global).
2. PWA is **only exposed on mobile/tablet** devices (UA + viewport gate).
3. The Save Offline action is **per booking/departure** (one button at the top of the Documents section), and is **gated by `departure.documents_ready = true`**.

Non-goals: custom install-prompt UI, service-worker cache versioning changes, fixes to the `systemDocs`/`departureDocs` parsing mismatch, iOS Safari storage limits.

## 2. Gates

Two server-side tenant flags drive Jinja emission; a client-side IIFE adds the viewport guard.

**Server-side (Jinja):**

```
pwa_active = company.config.pwa_enabled
             AND request.state.is_mobile

save_offline_active = pwa_active
                      AND company.config.offline_documents_enabled
                      AND departure.documents_ready

view_button_offline_cache_attr = company.config.offline_documents_enabled
```

**Client-side (IIFE in `<head>`, runs only when `pwa_active`):**

```
if matchMedia('(max-width: 1366px)') does NOT match:
    remove <link rel="manifest">
    window.__PWA_DISABLED__ = true   # pwa-offline.js short-circuits register()
```

The viewport guard is belt-and-suspenders for hybrid devices that lie about being mobile (e.g. iPad with desktop-class viewport, foldables). The server has no reliable way to know viewport pixel width on first paint; the client handles it.

- `pwa_enabled` drives manifest emission, service-worker registration, install affordance.
- `offline_documents_enabled` drives the `data-offline-cache` attribute on per-doc View buttons and the visibility of the bulk Save Offline button.
- `documents_ready` is a per-departure flag set by Operations (backend) once all docs are finalized.

Split-flag model matches Guest Portal `#163` exactly (decision: 2026-05-18 user check-in).

## 3. Architecture

### 3.1 Tenant schema (`apikey.json` + `CompanyConfig`)

Two new boolean fields per tenant, defaulting to `False`:

```python
# app/config.py — CompanyConfig
pwa_enabled: bool = False
offline_documents_enabled: bool = False
```

Parser (in `_load_company_configs` block of `app/config.py`) reads:

```python
"pwa_enabled": entry.get("PWAEnabled", False),
"offline_documents_enabled": entry.get("OfflineDocumentsEnabled", False),
```

`config/apikey.json` rollout (requires explicit user approval per project `CLAUDE.md` schema rule):

| Tenant     | PWAEnabled | OfflineDocumentsEnabled |
|------------|------------|-------------------------|
| WTGUIDE    | true       | true                    |
| (others)   | false      | false                   |

### 3.2 Mobile-detection middleware

New module `app/middleware/mobile_detection.py` — copy `guest-portal/app/middleware/mobile_detection.py` verbatim. UA regex matches iPhone, Android Mobile, iPad (legacy), Tablet, Mobile Safari, Opera Mini, IEMobile, Windows Phone, BlackBerry, Kindle, Silk. Sets `request.state.is_mobile`. Registered in `app/main.py` after the existing security middleware.

### 3.3 PWA head + script emission

`templates/partials/pwa_head.html` already exists from `#133`. Wrap the manifest `<link>`, `apple-mobile-web-app-capable`, `apple-touch-icon`, `theme-color`, and the viewport-guard `<script>` block inside:

```jinja
{% set pwa_active = company and company.config.pwa_enabled and request.state.is_mobile %}
{% if pwa_active %}
  ...existing PWA tags...
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
```

`templates/base.html` wraps `pwa-offline.js` (and the new `booking-save-offline.js`) in the same `{% if pwa_active %}` block. Anonymous renders and opted-out tenants emit no PWA surface.

### 3.4 Manifest route gate

`app/routes/pwa.py` `/manifest.json` endpoint adds a defense-in-depth 404:

```python
if not (config and config.pwa_enabled and getattr(request.state, "is_mobile", False)):
    raise HTTPException(status_code=404)
```

The existing neutral-fallback path for anonymous requests is preserved — anonymous requests still get the neutral manifest (no tenant identity), they just won't reach this handler in practice once the head-tag gate stops emitting the `<link>` on opted-out / desktop.

### 3.5 Service-worker register guard

`static/js/pwa-offline.js` `register()` checks `window.__PWA_DISABLED__` early-return, mirroring Guest Portal. No service-worker cache versioning change.

### 3.6 Trip departure template

`templates/pages/trip_departure.html` — both the Trip Documents and Departure Documents lists:

- **Per-row View button** replaces any existing per-row Save button:

  ```jinja
  <li class="list-group-item px-0 d-flex align-items-center justify-content-between gap-2">
      <span class="text-truncate">
          <em class="icon ni ni-file-pdf me-1 text-soft"></em>{{ doc.description }}
      </span>
      {% if doc.url %}
      <a href="{{ doc.url }}"
         target="_blank"
         rel="noopener"
         class="btn btn-sm btn-outline-light flex-shrink-0"
         {% if company.config.offline_documents_enabled %}data-offline-cache="true"{% endif %}>
          <em class="icon ni ni-eye"></em>
          <span class="view-doc-btn__label">View</span>
      </a>
      {% endif %}
  </li>
  ```

- **Bulk Save Offline header** above both lists in the Documents tab pane:

  ```jinja
  {% set save_offline_active = pwa_active and company.config.offline_documents_enabled and departure.documents_ready %}
  <div class="d-flex align-items-center justify-content-between mb-3 gap-2 flex-wrap">
      <h6 class="text-soft mb-0"><em class="icon ni ni-file-docs me-1"></em>Documents</h6>
      {% if save_offline_active %}
      <button type="button"
              id="booking-save-offline-btn"
              class="btn btn-outline-primary booking-save-offline-btn"
              data-departure-id="{{ departure.departure_id }}"
              aria-label="Save offline">
          <em class="icon ni ni-download me-1"></em>
          <span class="booking-save-offline-btn__label">Save offline</span>
      </button>
      <script id="booking-save-offline-data" type="application/json">
[
{%- set docs = (trip_documents | selectattr('url') | list) + (departure_documents | selectattr('url') | list) -%}
{%- for doc in docs -%}
{"url": {{ doc.url | tojson }}, "description": {{ (doc.description or '') | tojson }}}{% if not loop.last %},{% endif %}
{%- endfor -%}
]
      </script>
      {% endif %}
  </div>
  ```

The existing `save-offline-button.js` and any per-row `.save-offline-btn` markup are removed in the same commit (after a repo grep to confirm no other references).

### 3.7 Bulk-save JavaScript

`static/js/booking-save-offline.js` — port `guest-portal/static/js/booking-save-offline.js` verbatim. Depends only on `window.PWA.saveDocument` / `isDocumentCached` (provided by `pwa-offline.js`).

### 3.8 CSS

Append to the shared CSS file (`static/css/custom.css` or skin equivalent — single shared file, not per-skin):

- `.booking-save-offline-btn` block (idle / saving / saved / error states).
- `@media (min-width: 1367px) { .booking-save-offline-btn, [id="pwa-manifest-link"] { display: none } }` — desktop-hide boundary.
- `@media (max-width: 575.98px) { .view-doc-btn__label { display: none } }` — label collapses to icon-only on phone.

### 3.9 Schema + service mapping

`app/models/schemas.py` — add to `TripDeparture`:

```python
documents_ready: bool = False
```

`app/services/guide_service.py` (around line 540 `getDeparturePage` mapping):

```python
documents_ready=departure_response.get("documentsReady", False),
```

Until the backend ships the `documentsReady` field, the gate evaluates to `False` and the bulk Save Offline button never renders — re-verified 2026-05-18 against `https://test-2.tourcube.net/tourcube/guidePortal/getDeparturePage/64981`: still absent (response `requestStatus: "Access Denied"` without a guide session, and per Steve 2026-05-15 the field is not yet shipped). The rest of the PWA work (tenant toggle + mobile gate + View buttons) is **not blocked** by this.

### 3.10 Template context wiring

The trip departure route handler (`app/routes/guide.py`) passes the existing `company` and `departure` into the template; no new context keys required because `pwa_active` and `save_offline_active` are computed inline in Jinja from `company.config.*`, `request.state.is_mobile`, and `departure.documents_ready`.

## 4. Data Flow

**Per-request:**
1. `MobileDetectionMiddleware` sets `request.state.is_mobile` from UA.
2. Route handler resolves `company`, calls `guide_service.get_trip_departure(...)`.
3. Service hits `getDeparturePage`, maps `documentsReady → TripDeparture.documents_ready`.
4. Handler renders `trip_departure.html` with `company`, `request`, `departure`.
5. Template computes `pwa_active` and `save_offline_active` inline.

**Per-browser-load:**
1. `<head>` emits PWA tags + viewport-guard IIFE (only when `pwa_active`).
2. Viewport guard runs at >1366px → removes manifest link, sets `window.__PWA_DISABLED__ = true`.
3. `pwa-offline.js` checks `__PWA_DISABLED__` before `navigator.serviceWorker.register()`.
4. `booking-save-offline.js` reads `#booking-save-offline-data` JSON block, wires button click → loops docs through `window.PWA.saveDocument(...)`.
5. View-button click is handled by the existing delegated listener in `pwa-offline.js`: online → new tab, offline → cached blob from IndexedDB.

**Manifest route:**
- `/manifest.json` → 404 when `pwa_enabled=False` or `is_mobile=False`. Anonymous request → existing neutral fallback preserved.

## 5. Testing & Smoke

### 5.1 Unit tests (`tests/test_pwa_gating.py`, new)

- **UA classifier:** parameterized iPhone, Android, iPad legacy, Tablet, Mobile Safari, Opera Mini, IEMobile, Windows Phone, BlackBerry, Kindle, Silk → `True`; Mac, Windows desktop, Linux desktop → `False`.
- **Manifest 4-scenario matrix:** `(pwa_enabled, is_mobile) ∈ {(T,T),(T,F),(F,T),(F,F)}` → only `(T,T)` returns 200.
- **`apikey.json` contract:** every tenant entry must have `PWAEnabled` and `OfflineDocumentsEnabled` boolean keys.
- **`CompanyConfig` parser:** missing keys → defaults `False`.

### 5.2 Integration tests

- Template render with `(pwa_enabled=True, is_mobile=True, offline_documents_enabled=True, documents_ready=True)` → bulk Save Offline button + per-doc View buttons (with `data-offline-cache="true"`) + JSON data block all present.
- Same with `documents_ready=False` → View buttons present, bulk Save Offline absent.
- Same with `pwa_enabled=False` → no manifest, no SW script, no Save Offline button; View buttons present **without** `data-offline-cache` attr.

### 5.3 Smoke matrix (post-deploy)

Mirror Guest Portal `#163`:

| Block       | What                                                                          | Method                                     |
|-------------|-------------------------------------------------------------------------------|--------------------------------------------|
| 1           | `/manifest.json` per-tenant × per-UA matrix                                   | curl with iPhone + Desktop UAs             |
| 2           | Base template emission gate (markers present/absent per gate)                 | curl HTML + grep                           |
| 3           | Trip departure template render (PWA-on + docs ready)                          | Jinja unit render                          |
| 4           | Desktop Playwright DOM check                                                  | Playwright nav                             |
| 5           | Disabled tenant 404                                                           | curl                                       |
| 6           | Viewport guard JS at 320 / 768 / 1024 / 1366 / 1367 / 1920px                  | Playwright `evaluate`                      |
| 7           | pytest                                                                        | local                                      |
| 8           | CSS desktop-hide at 1367px boundary                                           | Playwright `getComputedStyle`              |
| iPhone real | Install affordance → Save Offline → IndexedDB → airplane mode → View opens   | physical device + Web Inspector over cable |

Guide login for the iPhone-real block: per `TOURCUBE/Credentials.md` → `tourcube-guideportal-guide-test`, user `robfnoonan@hotmail.com`, departure where backend has set `documentsReady = true` (coordinate with Steve once the field ships).

## 6. Acceptance Criteria

- Tenant with `PWAEnabled=False`: portal renders as a plain website; no manifest, no SW, no Save Offline UI, no `data-offline-cache` on View buttons; `/manifest.json` → 404.
- Tenant with `PWAEnabled=True` on desktop UA or viewport >1366px: no PWA surface; no Save Offline button; View buttons still rendered without `data-offline-cache`.
- Tenant with `PWAEnabled=True` on mobile/tablet ≤1366px: manifest served, SW registered, install affordance shown, Save Offline button at the top of the Documents section **iff** `OfflineDocumentsEnabled=True AND departure.documents_ready=True`.
- Document rows render as: icon + plain-text description (left) + `[👁 View]` button (right). No inline `<a>` styling on the description.
- Clicking the bulk Save Offline button caches every document (trip + departure) for that departure via `window.PWA.saveDocument`.
- Clicking a View button: online → new tab; offline (with prior cache) → cached blob from IndexedDB.
- `pytest` green; new tests cover the gating matrix (UA classifier, manifest 4-scenario, `apikey.json` contract).

## 7. Rollout & Risks

**Branching.** Branch off `origin/main` (commit on `feat/160-pwa-toggle-mobile-booking-save`). `#148` still in flight on `feature/148-remove-default-tenant-fallbacks`; rebase if both touch `app/config.py`. Memory rule: never reuse a merged branch.

**`apikey.json` schema change.** Per project `CLAUDE.md`: **explicit user approval required** before editing `config/apikey.json` (shared tenant config). Plan touches it once for the WTGUIDE = true, others = false rollout.

**Conflict with `#148`.** Both branches edit `app/config.py`. Strategy: branch from current `main` now; rebase onto `main` after `#148` lands.

**Stale SW on opted-out tenants.** If a tenant flips `PWAEnabled=False` after a previous opt-in, browsers that already registered the SW will keep it until the SW self-unregisters or the user clears storage. Acceptable — guest-portal carries the same trade-off and Steve is OK with it.

**Skin-specific CSS.** Multiple skin files exist; new `.booking-save-offline-btn` styles land once in the shared CSS to avoid per-theme drift.

**English-only in git.** All commits, branch names, PR titles/bodies, code comments stay in English (memory rule).

## 8. Out of Scope

- Custom `beforeinstallprompt` UI.
- Service-worker cache invalidation / versioning / background sync.
- Guest Portal counterpart (already shipped `#163`).
- `systemDocs` / `departureDocs` parsing mismatch (file separately).
- iOS Safari 50 MB cap and 7-day eviction (platform limit).

## 9. Open Items (carry into plan)

- **Final copy** (`Save offline` / `Saved offline` / `Saving…` / `Retry`) — Melissa pending on Jira DEVCUR-1638. Ship with the same placeholders used in Guest Portal `#163`; update in a follow-up when Melissa lands the final strings.
- **Backend `documentsReady` ETA** — Steve to route. Until then the gate stays `False` by default; no code change needed when the field ships, only a backend deploy.

---

**Owner:** Gilberto (implementing agent)
**Reviewers:** Steve (product), Melissa (copy)
**Related:** `#163` (Guest Portal counterpart — shipped 2026-05-18 via PRs #181 + #182)
