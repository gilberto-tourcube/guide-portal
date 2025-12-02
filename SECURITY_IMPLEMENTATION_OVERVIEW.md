# Tourcube Guide Portal - Security Implementation Overview

**Document Version**: 1.0
**Date**: December 2, 2025
**Target Audience**: Security Team / Infrastructure Team
**Project Status**: Development Complete, Ready for Production Deployment

---

## Executive Summary

The Tourcube Guide Portal is a modern web application built with FastAPI (Python) that serves as a multi-tenant portal for tour guides and vendors. This document outlines the security architecture, implementation decisions, and deployment requirements for security review and infrastructure planning.

**⚠️ SECURITY AUDIT FINDINGS**: This document has been updated based on an external security audit that identified several critical gaps between the documented and actual security implementation. See Section 5.1 for details.

**Actual Security Implementation Status**:
- ✅ Stateless architecture (no database, API-only)
- ⚠️ **Session management** - Cookies are **signed** (not encrypted), `Secure` flag not explicitly set
- ✅ Multi-company isolation
- ⚠️ **Role-based access control** - Session checked, but user ID not sent to API for authorization
- ❌ **HTTPS enforcement** - No HTTP→HTTPS redirect, no HSTS headers
- ❌ **Input validation** - Login form uses raw Form params without Pydantic validation
- ✅ Secure credential storage (git-ignored config files)

**Critical Security Gaps Identified**:
1. 🔴 **Session cookies not configured as Secure** (High severity)
2. 🔴 **No HTTPS enforcement or HSTS** (High severity)
3. 🔴 **User ID not sent in API calls** - backend cannot verify resource ownership (High severity)
4. 🟡 **Input validation minimal** - no Pydantic validation on login form (Medium severity)
5. 🟡 **CORS wildcard** - allows any origin (Medium severity)

---

## 1. Application Architecture

### 1.1 Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Backend Framework** | FastAPI | 0.121.3 | Web framework with async support |
| **Template Engine** | Jinja2 | 3.1.6 | Server-side HTML rendering |
| **HTTP Client** | HTTPX | 0.28.1 | Async API communication |
| **Session Management** | Starlette SessionMiddleware | 0.50.0 | Encrypted cookie-based sessions |
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
    ↓ Session Cookie (Encrypted)
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
5. POST to /auth/login (handler accepts raw Form parameters)
   ↓
6. POST to /tourcube/guidePortal/login with API key (header: "tc-api-key")
   ↓
7. API validates credentials, returns user type:
   - Type 1 = Guide
   - Type 2 = Vendor
   ↓
8. Create signed session cookie (not encrypted, just HMAC signed)
   ↓
9. Redirect to appropriate homepage:
   - Guide → /guide/home
   - Vendor → /vendor/home
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
    max_age=settings.session_max_age
)
```

**Session Configuration** (`.env`):
- **SECRET_KEY**: Required. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- **SESSION_COOKIE_NAME**: Default `guide_portal_session`
- **SESSION_MAX_AGE**: Default `86400` (24 hours)

**Cookie Attributes** (Starlette SessionMiddleware defaults):
- `HttpOnly`: Yes (prevents JavaScript access)
- `Secure`: **No** - Not explicitly set (⚠️ **Security Gap**)
- `SameSite`: Default behavior (not explicitly configured)
- `Max-Age`: 86400 seconds (configurable)

**⚠️ Security Note**: Cookies are **signed** (not encrypted) and the `Secure` flag is not explicitly enabled. This means:
- Session data is base64-encoded and signed with HMAC, but readable if intercepted
- Cookies may be sent over HTTP if `Secure` flag is not set by the platform
- Azure App Service may add `Secure` flag at the platform level for HTTPS connections

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

# ⚠️ LIMITATION: Service layer does NOT send user_id to API for most resources
```

**Resource Isolation** (⚠️ **Security Gaps**):
- ❌ **User ID not sent to API**: Most resource requests (trip, client) do not include the authenticated user's ID in API calls
- ❌ **No backend authorization check**: The portal checks session exists, but the API does not verify the user owns the resource
- ⚠️ **Relies on API-side validation**: Assumes the backend API enforces access control based on session/context
- ✅ **Session validation**: Portal does validate that user is authenticated before allowing access

**Actual Implementation** (from `app/services/guide_service.py`):
- API calls to `/getTripPage/{tripID}` and `/getClientPage/{clientID}` do NOT include `guide_id` or `vendor_id`
- Authorization relies entirely on backend API logic (if any)

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

**Limited Pydantic Validation** (from `app/models/schemas.py` and `app/routes/auth.py`):

```python
# Only login response is validated with Pydantic
class LoginRequest(BaseModel):
    username: str
    password: str
```

**Actual Validation Coverage** (⚠️ **Security Gaps**):
- ⚠️ **Login inputs NOT validated with Pydantic**: The login handler accepts raw `Form(...)` parameters without Pydantic validation
- ⚠️ **No regex/length checks on login**: `company_code` and `mode` are accepted as-is without validation
- ⚠️ **Query parameters unvalidated**: Most routes accept bare query params without Pydantic validation
- ✅ **API response validation**: Some API responses are validated with Pydantic models
- ✅ **SQL injection prevention**: No database access (stateless architecture)
- ✅ **XSS prevention**: Jinja2 auto-escaping enabled by default

**Actual Login Handler** (from `app/routes/auth.py`):
```python
@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    company_code: str = Form(...),
    mode: str = Form(...)
):
    # No Pydantic validation, no length checks, no regex patterns
```

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

**⚠️ Limited HTTPS Enforcement**:

**Outbound SSL Verification** (from `.env.example`):
```env
SSL_VERIFY=true  # Enforce SSL certificate verification for API calls
```

**Implementation** (from `app/services/api_client.py`):
```python
httpx.AsyncClient(
    verify=settings.ssl_verify,  # Always True in production
    timeout=30.0
)
```

**Scheme Rewriting (NOT Enforcement)** (from `app/main.py`):
```python
@app.middleware("http")
async def force_https_scheme(request, call_next):
    """Rewrite scheme to HTTPS when behind Azure proxy"""
    # Only rewrites the scheme, does NOT redirect HTTP to HTTPS
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response
```

**⚠️ Security Gaps**:
- ❌ **No HTTP→HTTPS redirect**: Application accepts both HTTP and HTTPS requests
- ❌ **No HSTS headers**: Strict-Transport-Security header not set
- ⚠️ **Relies on Azure**: Assumes Azure App Service handles HTTPS enforcement
- ✅ **URL generation**: Ensures generated URLs use HTTPS when behind proxy

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
    result = await auth_service.login(credentials)
except Exception as e:
    logger.error(f"Login failed: {str(e)}")  # Server log only
    return templates.TemplateResponse(
        "pages/login.html",
        {
            "error": "Invalid credentials or system error",  # Generic
            ...
        }
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
| 80 | HTTP | Internet | Redirects to HTTPS | Azure App Service auto-redirects |

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
    allow_origins=["*"],  # TODO: Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Production Recommendation**: Restrict `allow_origins` to specific domains

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
  - [ ] Update `allow_origins` in `app/main.py` to restrict domains

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
# Expected: HttpOnly=true
# Note: Secure flag may be set by Azure, not explicitly by application
# Note: SameSite not explicitly configured (uses browser/platform default)
```

---

## 5. Known Security Considerations

### 5.1 Critical Security Gaps (From Security Audit)

| Item | Severity | Current State | Impact | Recommended Fix |
|------|----------|---------------|--------|-----------------|
| **Session Cookies Not Secure** | 🔴 High | Cookies are signed but not encrypted; `Secure` flag not explicitly set | Cookies may be sent over HTTP; session data readable if intercepted | Add `https_only=True, secure=True` to SessionMiddleware |
| **No HTTPS Enforcement** | 🔴 High | No HTTP→HTTPS redirect; no HSTS headers | Users can access site over HTTP; vulnerable to downgrade attacks | Add middleware to redirect HTTP→HTTPS; add HSTS header |
| **Input Validation Missing** | 🟡 Medium | Login form params not validated with Pydantic; no length/regex checks | Potential for injection attacks; malformed inputs not rejected | Add Pydantic validation to all form inputs |
| **No User ID in API Calls** | 🔴 High | Trip/client API calls don't include authenticated user ID | Backend cannot verify user owns resource; potential unauthorized access | Send `user_id` in all resource API requests |
| **CORS Wildcard** | 🟡 Medium | `allow_origins=["*"]` allows any origin | Cross-origin attacks possible; CSRF vulnerability | Restrict to specific domains |

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
1. **Fix Session Cookie Security**: Add `https_only=True, secure=True, samesite="lax"` to SessionMiddleware
2. **Implement HTTPS Enforcement**: Add middleware to redirect HTTP→HTTPS and set HSTS headers
3. **Add Input Validation**: Implement Pydantic validation for all form inputs (especially login)
4. **Send User ID to API**: Include authenticated user ID in all resource API requests
5. **Restrict CORS**: Update `allow_origins` in `app/main.py` to specific domains only

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

### Key Corrections in v1.1
1. **Session cookies**: Changed from "encrypted + Secure" to "signed (not encrypted), Secure flag not explicitly set"
2. **HTTPS enforcement**: Changed from "enforced" to "scheme rewriting only, no redirect or HSTS"
3. **Input validation**: Changed from "all inputs validated with Pydantic" to "minimal validation, login uses raw Form params"
4. **Authorization**: Clarified that user ID is NOT sent to API in most resource requests
5. **API header**: Corrected header name from `TourcubeAPIKey` to `tc-api-key`
6. **Login URL**: Corrected from `/login` to `/auth/login`
7. **Health check response**: Corrected from `{"status": "ok"}` to `{"status": "healthy", "version": "..."}`
8. **Session data**: Corrected vendor session structure (no separate `vendor_name` field)

### Recommendation
**Before production deployment**, address the 5 critical security gaps identified in Section 5.1. These are not theoretical vulnerabilities but actual implementation gaps discovered through code review.

---

**End of Document**

*This document has been updated to accurately reflect the actual security implementation based on external security audit findings. For questions or clarifications, please contact the development team.*
