## `apikey.json` schema

This directory holds the per-tenant configuration consumed by `app/config.py:Settings._load_company_configs`. The live file (`config/apikey.json`) is gitignored because it carries production API keys; use `config/apikey.json.example` as the schema reference when standing up a new environment.

### Per-tenant fields

Beyond the existing `CompanyID`, `Test`, `Production`, `TestURL`, `ProductionURL`, `TestDomains`, `ProductionDomains`, `HTMLHeader`, `HTMLFooter`, `Logo`, `LoginBackground`, `TourcubeOnline`, `TourcubeRootDrive`, `SkinName`, ticket #160 adds:

- `PWAEnabled` (bool, default `false`): when true, the tenant gets the PWA install surface (manifest, service worker, install affordance) on mobile UAs only.
- `OfflineDocumentsEnabled` (bool, default `false`): when true, the View buttons on `pages/trip_departure.html` carry `data-offline-cache="true"` and the booking-level Save Offline button renders (also requires `PWAEnabled=true` and `departure.documents_ready=true`).

After updating `apikey.json` in any environment, restart the app — the parser caches configs at startup.
