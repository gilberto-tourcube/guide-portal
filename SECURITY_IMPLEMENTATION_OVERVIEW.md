# Tourcube Guide Portal - Security Implementation Overview

**Document Version**: 1.2
**Date**: December 2, 2025
**Target Audience**: Security Team / Infrastructure Team
**Project Status**: Development Complete, Ready for Production Deployment

---

## Executive Summary

The Tourcube Guide Portal is a modern web application built with FastAPI (Python) that serves as a multi-tenant portal for tour guides and vendors. This document outlines the security architecture, implementation decisions, and deployment requirements for security review and infrastructure planning.

**Actual Security Implementation Status** (post-remediation):
- ✅ Stateless architecture (no database, API-only)
- ✅ **Session management** - Cookies are signed (not encrypted), `Secure` via https_only + `SameSite=Lax`
- ✅ Multi-company isolation
- ⚠️ **Role-based access control** - Session checked and `userId` forwarded to API; backend still must enforce ownership
- ✅ **HTTPS enforcement** - HTTP→HTTPS redirect and HSTS middleware (skipped in debug)
- ✅ **Input validation** - Login form uses Pydantic + length/regex checks
- ✅ Secure credential storage (git-ignored config files)

**Remediated Audit Items (Section 5.1)**:
1. 🔄 **Session cookies** - now `https_only=True`, `SameSite=Lax`; still signed (not encrypted)
2. 🔄 **HTTPS enforcement** - redirect + HSTS middleware added
3. 🔄 **User ID forwarding** - `userId` sent on resource API calls
4. 🔄 **Input validation** - login handled via Pydantic model
5. 🔄 **CORS** - allow-list via settings (default: same-origin only)

---

## 1. Application Architecture

### 1.1 Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Backend Framework** | FastAPI | 0.121.3 | Web framework with async support |
| **Template Engine** | Jinja2 | 3.1.6 | Server-side HTML rendering |
| **HTTP Client** | HTTPX | 0.28.1 | Async API communication |
| **Session Management** | Starlette SessionMiddleware | 0.50.0 | Signed, Secure, SameSite=Lax cookies (not encrypted) |
| **Data Validation** | Pydantic | 2.12.4 | Request/response validation |
| **ASGI Server** | Uvicorn | 0.38.0 | ASGI server (development) |
| **WSGI Server** | Gunicorn | 23.0.0 | Production server |
| **Python Version** | Python | 3.13 | Runtime environment |

### 1.2 Architectural Principles

1. **Stateless Design**: No local database; all data fetched from external Tourcube API
2. **API Gateway Pattern**: Acts as a secure gateway between users and backend API
3. **Multi-Tenancy**: Supports multiple companies with isolated configurations
4. **RESTful Resource Routing**: Resource-based URLs (not user-type based)
5. **Server-Side Rendering**: All HTML generated server-side (no SPA vulnerabilities)

### 1.3 Data Flow

```
User Browser
    ↓ HTTPS
[Azure App Service / Reverse Proxy]
    ↓ X-Forwarded-Proto: https
[FastAPI Application]
    ↓ Session Cookie (Signed, Secure)
[Session Middleware]
    ↓ Validation
[Route Handlers]
    ↓ Business Logic
[Service Layer]
    ↓ HTTPS + API Key
[External Tourcube API]
```

---

## 2. Security Implementation

### 2.1 Authentication & Authorization

#### Authentication Flow

```
1. User → /auth/login?company_code=WTGUIDE&mode=Test
   ↓
2. Load company config from config/apikey.json
   ↓
3. Render branded login page with company logo and skin
   ↓
4. User submits credentials (username + password)
   ↓
5. POST to /auth/login (Pydantic-validated form: length + regex)
   ↓
6. POST to /tourcube/guidePortal/login with API key (header: "tc-api-key")
   ↓
7. API validates credentials, returns user type:
   - Type 1 = Guide
   - Type 2 = Vendor
   ↓
8. Create signed session cookie (https_only, SameSite=Lax; not encrypted)
   ↓
9. Redirect to appropriate homepage:
   - Guide → /guide/home
   - Vendor → /vendor/home

**Optional Support Link (guide_hash)**:
- If the query includes `guide_hash`, `/guide/home` resolves it via `/tourcube/v1/clientHash/{guide_hash}` to obtain `guide_id` and bootstraps a guide session (bypassing form login) for support staff.
```

#### Session Management

**Session Storage**: Cookie-based (no server-side storage)

**Session Data Structure** (from `app/routes/auth.py`):
```python
session = {
    "authenticated": True,
    "user_type": 1 or 2,  # 1=Guide, 2=Vendor
    "user_role": "Guide" or "Vendor",
    "company_code": "WTGUIDE",
    "mode": "Test" or "Production",

    # Normalized user data (for all types):
    "user_name": "John Doe" or "Vendor Name",
    "user_email": "john@example.com" or None,
    "user_image": "https://..." or None,

    # For Guides (Type 1):
    "guide_id": "12345",
    "guide_first_name": "John",
    "guide_last_name": "Doe",
    "guide_email": "john@example.com",

    # For Vendors (Type 2):
    "vendor_id": "67890"
    # Note: vendor_name is NOT stored separately, only in user_name
}
```

**Session Security** (from `app/main.py`):
```python
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    https_only=not settings.debug,
    same_site="lax"
)
```

**Session Configuration** (`.env`):
- **SECRET_KEY**: Required. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- **SESSION_COOKIE_NAME**: Default `guide_portal_session`
- **SESSION_MAX_AGE**: Default `86400` (24 hours)

**Cookie Attributes**:
- `HttpOnly`: Yes (prevents JavaScript access)
- `Secure`: Yes in production (`https_only=True` when not in debug)
- `SameSite`: Lax (explicitly configured)
- `Max-Age`: 86400 seconds (configurable)

**Security Note**: Cookies are **signed** (not encrypted). `https_only=True` sets the Secure flag; session contents remain readable if intercepted in plaintext.

#### Authorization Model

**Role-Based Access Control (RBAC)**:

| User Type | Role | Access |
|-----------|------|--------|
| Type 1 | Guide | `/guide/home`, `/trip/{id}`, `/departure/{id}`, `/client/{id}` |
| Type 2 | Vendor | `/vendor/home`, `/trip/{id}`, `/departure/{id}`, `/client/{id}` |

**Access Control Implementation** (from `app/routes/resources.py`):
```python
# In routes/resources.py
user_id = request.session.get("guide_id") or request.session.get("vendor_id")
if not user_id:
    return RedirectResponse(url="/login")

# user_id forwarded to service layer to include in downstream API calls
```

**Resource Isolation**:
- ✅ `userId` forwarded on trip, departure, and client API calls
- ⚠️ Backend API must still enforce ownership/authorization using the forwarded ID
- ✅ Session validation performed before calling services

---

### 2.2 Multi-Company Configuration

#### Company Isolation

**Configuration File**: `config/apikey.json` (git-ignored)

```json
{
  "TourcubeAPIKey": [
    {
      "CompanyID": "WTGUIDE",
      "Logo": "wilderness-travel-logo.png",
      "TourcubeOnline": true,
      "SkinName": "theme-bluelite",
      "Test": "TEST_API_KEY_HERE",
      "TestURL": "https://test-api.tourcube.com",
      "Production": "PRODUCTION_API_KEY_HERE",
      "ProductionURL": "https://api.tourcube.com"
    }
  ]
}
```

**Configuration Loading** (from `app/config.py`):
- API keys loaded at runtime based on `company_code` and `mode`
- Caching mechanism prevents repeated file reads
- Invalid company codes raise `InvalidCompanyCodeError`
- Theme extraction from `SkinName` or `HTMLHeader` fields

**Security Notes**:
- API keys stored in file outside version control (`.gitignore`)
- Each company has separate Test and Production API keys
- Company isolation at API level (not application level)
- Logo files stored in `static/images/` directory
- File should have restricted permissions: `chmod 600 config/apikey.json`

---

### 2.3 Input Validation & Sanitization

#### Pydantic Models

**Login Validation (implemented)**:

```python
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)
    company_code: str = Field(..., min_length=1, max_length=50)
    mode: str = Field(..., pattern="^(Test|Production)$")

@router.post("/login")
async def login_submit(
    request: Request,
    form_data: LoginRequest = Depends(_login_form_dependency)
):
    ...
```

**Validation Coverage**:
- ✅ Login form validated with Pydantic (length + regex)
- ✅ `company_code` and `mode` validated via Query/Forms
- ✅ API responses validated with Pydantic models
- ✅ SQL injection prevention: No database access (stateless)
- ✅ XSS prevention: Jinja2 auto-escaping enabled
- ⚠️ Other routes use parameter typing only (no dedicated Pydantic models)

#### Template Security

**Jinja2 Auto-Escaping**: Enabled by default

```python
# All variables automatically escaped
{{ user.name }}  # Safe: <script> becomes &lt;script&gt;

# Explicit safe marking only when needed
{{ content | safe }}  # Only for trusted HTML
```

---

### 2.4 API Communication Security

#### HTTPS Enforcement

**Outbound SSL Verification** (from `.env.example`):
```env
SSL_VERIFY=true  # Enforce SSL certificate verification for API calls
```

**Implementation** (from `app/main.py`):
```python
@app.middleware("http")
async def enforce_https_and_hsts(request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"

    is_https = request.scope.get("scheme") == "https"
    if not is_https and not settings.debug:
        https_url = request.url.replace(scheme="https")
        return RedirectResponse(url=str(https_url), status_code=307)

    response = await call_next(request)

    if is_https and not settings.debug:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains; preload"
        )

    return response
```

**Notes**:
- ✅ HTTP→HTTPS redirect enforced when not in debug mode
- ✅ HSTS added on HTTPS responses (skipped in debug)
- ✅ Proxy-aware via `X-Forwarded-Proto`

#### API Key Management

**Storage**: `config/apikey.json` (git-ignored, file permissions 600)

**Access Pattern** (from `app/config.py` and `app/services/api_client.py`):
```python
# API key loaded at runtime based on company_code and mode
config = settings.get_company_config(company_code, mode)
api_key = config.api_key
api_url = config.api_url

# API key sent in header (not URL) - from api_client.py
headers = {
    "tc-api-key": api_key,  # Note: header name is "tc-api-key"
    "Content-Type": "application/json",
    "User-Agent": f"{settings.app_name}/{settings.app_version}"
}
```

**Note**: The actual header name is `tc-api-key`, not `TourcubeAPIKey` as might be expected.

**Key Rotation Process**:
1. Update `config/apikey.json` with new key
2. Restart application (no code changes needed)
3. Old sessions remain valid (keys are per-company)

---

### 2.5 Error Handling & Information Disclosure

#### Error Messages

**Production Behavior**:
- Generic error messages to users: "An error occurred. Please try again."
- Detailed errors logged server-side only
- No stack traces exposed to users
- No API endpoint URLs in error messages

**Implementation** (from `app/routes/auth.py`):
```python
try:
    login_response = await auth_service.login(...)
except httpx.HTTPError as e:
    logger.error("Login API error: %s", e)  # Server log only
    return RedirectResponse(
        url=f"/auth/login?company_code={...}&mode={...}&error=api_error",
        status_code=303
    )
except Exception as e:
    logger.error("Login error: %s", e)  # Server log only
    return RedirectResponse(
        url=f"/auth/login?company_code={...}&mode={...}&error=unexpected_error",
        status_code=303
    )
```

---

## 3. Deployment Configuration

### 3.1 Deployment Platform

**Current Deployment**: Azure App Service via GitHub Actions

**Workflow File**: `.github/workflows/main_guideportal.yml`

#### GitHub Actions CI/CD Pipeline

```yaml
name: Build and deploy Python app to Azure Web App - guideportal

on:
  push:
    branches:
      - main
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python version
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Create and Start virtual environment and Install dependencies
        run: |
          python -m venv antenv
          source antenv/bin/activate
          pip install -r requirements.txt

      - name: Upload artifact for deployment jobs
        uses: actions/upload-artifact@v4
        with:
          name: python-app
          path: |
            .
            !antenv/

  deploy:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Download artifact from build job
        uses: actions/download-artifact@v4
        with:
          name: python-app

      - name: 'Deploy to Azure Web App'
        uses: azure/webapps-deploy@v3
        with:
          app-name: 'guideportal'
          slot-name: 'Production'
          publish-profile: ${{ secrets.AZUREAPPSERVICE_PUBLISHPROFILE_8FEF5CADCDDC46A2ADF0482D22337C6E }}
```

**Deployment Process**:
1. Code pushed to `main` branch triggers workflow
2. Python 3.13 environment created
3. Dependencies installed from `requirements.txt`
4. Application artifact uploaded (excluding virtual environment)
5. Artifact deployed to Azure App Service via publish profile
6. Oryx build engine handles compilation on Azure platform

**Azure App Service Configuration**:
- **App Name**: `guideportal`
- **Slot**: `Production`
- **Build Engine**: Oryx (SCM_DO_BUILD_DURING_DEPLOYMENT=true)
- **Authentication**: Publish profile stored in GitHub Secrets

---

### 3.2 Environment Variables

**Required Configuration** (from `.env.example`):

```env
# Session Configuration (REQUIRED)
SECRET_KEY=your_secret_key_here_generate_with_secrets_token_urlsafe_32
SESSION_COOKIE_NAME=guide_portal_session
SESSION_MAX_AGE=86400

# Company Configuration (Optional - has defaults)
COMPANY_CODE=WTGUIDE
MODE=Test

# API Configuration Path (Optional - has default)
API_KEY_JSON_PATH=./config/apikey.json

# Application Settings (Optional - has defaults)
DEBUG=false
APP_NAME=Tourcube Guide Portal
APP_VERSION=1.0.0

# Server Configuration (Optional - has defaults)
HOST=0.0.0.0
PORT=8000
RELOAD=false

# Security (Optional - has default)
SSL_VERIFY=true
ALLOWED_ORIGINS=[]  # JSON list of allowed origins for CORS
```

**Generate Secret Key**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Azure App Service Environment Variables**:
- Configure in Azure Portal: Configuration → Application Settings
- Add all variables from `.env.example`
- Ensure `SECRET_KEY` is properly generated
- Set `DEBUG=false` for production

---

### 3.3 File System Requirements

**Directory Structure**:
```
/app/
├── config/
│   └── apikey.json           # Permissions: 600 (read/write owner only)
├── static/
│   └── images/
│       ├── logo.png
│       └── *.png             # Company logos
├── app/                      # Application code
├── templates/                # Jinja2 templates
└── requirements.txt          # Python dependencies
```

**File Permissions** (if deploying outside Azure):
```bash
chmod 600 config/apikey.json
chmod 600 .env
chmod 644 static/**/*
chmod 755 app/
```

**Note**: Azure App Service manages file permissions automatically.

---

### 3.4 Network Requirements

#### Inbound Traffic

| Port | Protocol | Source | Purpose | Notes |
|------|----------|--------|---------|-------|
| 443 | HTTPS | Internet | Web traffic | Azure App Service handles SSL |
| 80 | HTTP | Internet | Redirects to HTTPS | Application middleware + Azure redirect to HTTPS |

#### Outbound Traffic

| Destination | Protocol | Port | Purpose |
|-------------|----------|------|---------|
| api.tourcube.com | HTTPS | 443 | Production API calls |
| test-api.tourcube.com | HTTPS | 443 | Test API calls |

**Azure App Service Notes**:
- Inbound traffic handled by Azure infrastructure
- HTTPS automatically enforced
- SSL certificates managed by Azure
- No direct port configuration needed

---

### 3.5 Azure-Specific Configuration

#### CORS Configuration (from `app/main.py`)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # Default: [] (same-origin only)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Production Configuration**: Set `ALLOWED_ORIGINS` environment variable (JSON list) to the approved domains.

#### Static Files

```python
app.mount("/static", StaticFiles(directory="static"), name="static")
```

- Static files served directly by FastAPI
- Azure App Service caches static content automatically
- No separate CDN configuration in current deployment

---

## 4. Security Checklist

### 4.1 Pre-Deployment Checklist

- [ ] **Environment Variables (Azure App Service)**
  - [ ] `SECRET_KEY` generated with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
  - [ ] `DEBUG=false` in production
  - [ ] `SSL_VERIFY=true` in production
  - [ ] `SESSION_MAX_AGE` appropriate (default: 24 hours)

- [ ] **Configuration Files**
  - [ ] `config/apikey.json` created with production API keys
  - [ ] All company logos uploaded to `static/images/`
  - [ ] Verify `apikey.json` structure matches expected format

- [ ] **GitHub Secrets**
  - [ ] `AZUREAPPSERVICE_PUBLISHPROFILE_*` configured
  - [ ] Publish profile downloaded from Azure Portal

- [ ] **Azure App Service**
  - [ ] HTTPS enforced (Azure handles automatically)
  - [ ] Custom domain configured (if needed)
  - [ ] Environment variables configured in App Settings
  - [ ] SCM_DO_BUILD_DURING_DEPLOYMENT = true (for Oryx build)

- [ ] **CORS Configuration**
  - [ ] Set `ALLOWED_ORIGINS` to approved domains (JSON list)

### 4.2 Post-Deployment Validation

```bash
# 1. Health check
curl https://guideportal.azurewebsites.net/health
# Expected: {"status": "healthy", "version": "1.0.0"}

# 2. SSL verification
openssl s_client -connect guideportal.azurewebsites.net:443
# Expected: Valid Azure SSL certificate

# 3. Login flow
# Navigate to: https://guideportal.azurewebsites.net/auth/login?company_code=WTGUIDE&mode=Production
# Expected: Branded login page → successful login → redirect to /guide/home or /vendor/home

# 4. Session cookie attributes
# Open browser DevTools → Application → Cookies
# Expected: HttpOnly=true, Secure=true, SameSite=Lax
```

---

## 5. Known Security Considerations

### 5.1 Audit Items (Current Status)

| Item | Severity | Current State | Impact | Status/Action |
|------|----------|---------------|--------|---------------|
| **Session Cookies Security** | 🔴→🟡 | Signed (not encrypted), `https_only=True`, `SameSite=Lax` | Contents readable if intercepted in plaintext; Secure flag now enforced | Mitigated via Secure + SameSite; encryption not implemented (accepted) |
| **HTTPS Enforcement** | 🔴→🟢 | Middleware redirects HTTP→HTTPS and sets HSTS (non-debug) | Downgrade risk addressed | Implemented |
| **Input Validation** | 🟡→🟢 | Login form validated with Pydantic + regex/length | Malformed input rejected | Implemented |
| **User ID in API Calls** | 🔴→🟡 | `userId` forwarded on trip/departure/client requests | Backend must enforce ownership with provided ID | Forwarding implemented; backend enforcement required |
| **CORS Wildcard** | 🟡→🟢 | `allowed_origins` allow-list from settings (default: []) | Cross-origin limited to configured domains | Implemented |

### 5.2 Additional Limitations

| Item | Status | Mitigation |
|------|--------|-----------|
| **Authentication Middleware** | ❌ Not implemented | Each route checks session manually |
| **Rate Limiting** | ❌ Not implemented | Consider Azure Application Gateway |
| **Account Lockout** | ❌ Not implemented | Backend API responsibility |
| **Password Reset** | ⚠️ Frontend only (backend pending) | Backend API implementation needed |
| **MFA Support** | ❌ Not implemented | Backend API responsibility |
| **CSRF Tokens** | ⚠️ SessionMiddleware provides basic protection | Consider explicit tokens for forms |
| **Audit Logging** | ⚠️ Basic logging only | Implement Azure Application Insights |

### 5.3 Recommended Enhancements

#### Phase 1 (Critical - Security Audit Findings)
1. **Fix Session Cookie Security**: ✅ `https_only=True`, `SameSite=Lax` (still signed, not encrypted)
2. **Implement HTTPS Enforcement**: ✅ Redirect + HSTS middleware (non-debug)
3. **Add Input Validation**: ✅ Pydantic validation for login form
4. **Send User ID to API**: ✅ `userId` forwarded on resource requests; backend must enforce
5. **Restrict CORS**: ✅ Allow-list via settings (`ALLOWED_ORIGINS`)

#### Phase 2 (High Priority)
6. **Authentication Middleware**: Implement `@require_auth` decorator
7. **Azure Application Insights**: Enable for structured logging and monitoring
8. **Error Pages**: Custom 404, 500, 403 pages (no information disclosure)
9. **API Key Header Standardization**: Document actual header name `tc-api-key`

#### Phase 3 (Medium Priority)
10. **Rate Limiting**: Configure Azure Application Gateway or Azure Front Door
11. **CSRF Tokens**: Explicit tokens for all POST forms
12. **Session Timeout Warning**: JavaScript warning before session expires

#### Phase 4 (Low Priority)
13. **Content Security Policy**: Add CSP headers via middleware
14. **Security Scanning**: Automated vulnerability scanning (GitHub Security, Dependabot)
15. **Secrets Management**: Azure Key Vault for `SECRET_KEY` and API keys

---

## 6. External API Endpoints Consumed

### Authentication Endpoints
```
POST /tourcube/guidePortal/login
GET  /tourcube/guidePortal/forgotUserName/{email}
GET  /tourcube/v1/clientHash/{guide_hash}   # guide_hash -> guide_id (support bypass)
```

### Guide Endpoints
```
GET  /tourcube/guidePortal/getGuideHomepage/{guideID}
GET  /tourcube/guidePortal/getGuideForms/{guideID}/{tripDepartureID}
```

### Vendor Endpoints
```
GET  /tourcube/guidePortal/getVendorHomepage/{vendorID}
```

### Resource Endpoints (Accessible by Guides and Vendors)
```
GET  /tourcube/guidePortal/getDeparturePage/{tripDepartureID}
GET  /tourcube/guidePortal/getTripPage/{tripID}
GET  /tourcube/guidePortal/getClientPage/{clientID}
```

**API Communication**:
- All requests use HTTPS
- API key sent via `tc-api-key` header (not `TourcubeAPIKey`)
- Timeout: 30 seconds (configurable)
- SSL verification: Enabled (configurable via `SSL_VERIFY`)
- User-Agent: `{APP_NAME}/{APP_VERSION}` included in headers

---

## 7. Incident Response

### 7.1 Security Incident Procedures

**If API Key Compromised**:
1. Immediately update `config/apikey.json` with new key
2. Redeploy application (push to `main` branch or manual deployment)
3. Rotate `SECRET_KEY` to invalidate all sessions
4. Notify backend API provider

**If Session Key Compromised**:
1. Generate new `SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Update Azure App Service environment variable
3. Restart application (all users logged out)
4. Notify affected users

**If Unauthorized Access Detected**:
1. Review Azure Application Insights logs for suspicious activity
2. Check Azure App Service logs for attack patterns
3. Block offending IPs at Azure level (if needed)
4. Audit all user sessions and invalidate if needed

### 7.2 Log Review

**Azure Application Insights** (recommended setup):
- Enable Application Insights in Azure Portal
- Configure log retention policies
- Set up alerts for errors and anomalies

**Daily**:
- Check error logs for unusual patterns
- Review failed login attempts

**Weekly**:
- Analyze access patterns
- Review session creation/destruction rates

**Monthly**:
- Security audit of configurations
- Review and rotate API keys (if policy requires)

---

## 8. Contact & Support

### 8.1 Technical Contacts

| Role | Responsibility |
|------|----------------|
| **Development Team** | Application code, bug fixes |
| **Infrastructure Team** | Azure deployment, configuration |
| **Security Team** | Security review, incident response |
| **Tourcube API Support** | API issues, key rotation |

### 8.2 Documentation References

- **Application README**: `README.md`
- **Quick Start Guide**: `QUICKSTART.md`
- **Implementation Details**: `checkpoint.md`
- **GitHub Workflow**: `.github/workflows/main_guideportal.yml`

---

## 9. Approval & Sign-Off

**Document Reviewed By**:

| Name | Role | Date | Signature |
|------|------|------|-----------|
| | Security Team Lead | | |
| | Infrastructure Team Lead | | |
| | Development Team Lead | | |

**Deployment Approval**:

| Environment | Approved By | Date | Notes |
|-------------|-------------|------|-------|
| Test | | | |
| Staging | | | |
| Production | | | |

---

## 10. Document Revision History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-12-02 | Initial document creation | Development Team |
| 1.1 | 2025-12-02 | **Security audit corrections** - Updated to reflect actual implementation vs. documented claims | Development Team |
| 1.2 | 2025-12-02 | Implemented remediation (HTTPS redirect + HSTS, Secure cookies, login validation, userId forwarding, CORS allow-list) | Development Team |

### Key Corrections in v1.1/v1.2
1. **Session cookies**: Clarified as signed (not encrypted) and now set Secure via `https_only` + `SameSite=Lax`
2. **HTTPS enforcement**: Added middleware for HTTP→HTTPS redirect + HSTS (non-debug)
3. **Input validation**: Login now validated with Pydantic + regex/length checks
4. **Authorization**: `userId` now forwarded on resource API requests
5. **API header**: Corrected header name from `TourcubeAPIKey` to `tc-api-key`
6. **Login URL**: Corrected from `/login` to `/auth/login`
7. **Health check response**: Corrected from `{"status": "ok"}` to `{"status": "healthy", "version": "..."}`
8. **Session data**: Corrected vendor session structure (no separate `vendor_name` field)
9. **Security remediations**: Added HTTPS redirect + HSTS, Secure + SameSite cookies, Pydantic login validation, `userId` forwarding, and CORS allow-list configuration

### Recommendation
**Before production deployment**, address the 5 critical security gaps identified in Section 5.1. These are not theoretical vulnerabilities but actual implementation gaps discovered through code review.

---

**End of Document**

*This document has been updated to accurately reflect the actual security implementation based on external security audit findings. For questions or clarifications, please contact the development team.*
