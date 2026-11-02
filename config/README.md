## `apikey.json` schema

This directory holds the per-tenant configuration consumed by `app/config.py:Settings._load_company_configs`. The live file (`config/apikey.json`) is gitignored because it carries production API keys; use `config/apikey.json.example` as the schema reference when standing up a new environment.

### Per-tenant fields

Beyond the existing `CompanyID`, `Test`, `Production`, `TestURL`, `ProductionURL`, `TestDomains`, `ProductionDomains`, `HTMLHeader`, `HTMLFooter`, `Logo`, `LoginBackground`, `TourcubeOnline`, `TourcubeRootDrive`, `SkinName`, ticket #160 adds:

- `PWAEnabled` (bool, default `false`): when true, the tenant gets the PWA install surface (manifest, service worker, install affordance) on mobile UAs only.
- `OfflineDocumentsEnabled` (bool, default `false`): when true, the View buttons on `pages/trip_departure.html` carry `data-offline-cache="true"` and the booking-level Save Offline button renders (also requires `PWAEnabled=true` and `departure.documents_ready=true`).
- `PWAThemeColor` (optional `#RRGGBB`): explicit manifest color; an unknown skin otherwise receives the neutral fallback color.

After updating `apikey.json` in any environment, restart the app — the parser caches configs at startup.

## `TENANT_REDIRECTS` app setting (per-tenant redirect switch)

Sends every request of a tenant to another https origin, keeping path and query, without a deploy. Used for the INCA V7 -> V8 cutover, where INCA guides move from the shared generic host to `inca.guideportal.tourcube.net`.

- Unset or empty (default): off. The app behaves exactly as if the switch did not exist.
- On: a JSON object of company code to origin, e.g. `{"INCA": "https://inca.guideportal.tourcube.net"}`.
- A request is redirected when its tenant resolves to a listed company code, using the same precedence as the rest of the app: `company_code`/`companyCode` in the query (any case), then the tenant already in the session (a guide logged in before the switch was turned on must not keep writing to V7), then the host map. This includes guide_hash links: the redirect runs before the V7 hash lookup, so the hash is carried to the new host untouched.
- `/health` and `/static/` are never redirected.
- Response is `307`: temporary and method-preserving (a POST keeps its method and body). Never `301`/`308`, which browsers cache and would make the switch irreversible.
- The destination comes only from this setting. Only a bare https origin is accepted (no path, query, fragment or credentials); anything else is ignored with a warning, as is invalid JSON, so a typo cannot stop the shared app from booting.
- A request already on the destination host is never redirected (no loop).
- Other tenants are untouched.
- Azure App Service restarts the app whenever an app setting changes: that is how the switch is turned on or off (set the value, or set it empty), a brief restart for every tenant on that app. The setting is read at startup.
