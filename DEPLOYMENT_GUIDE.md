# Tourcube Guide Portal - Deployment Guide

**Document Version**: 1.0
**Date**: December 2, 2025
**Target Audience**: Infrastructure Team / DevOps

---

## Table of Contents

1. [Technology Stack](#1-technology-stack)
2. [Environment Configuration](#2-environment-configuration)
3. [Deployment Process](#3-deployment-process)
4. [Network Requirements](#4-network-requirements)
5. [Post-Deployment Validation](#5-post-deployment-validation)

---

## 1. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Backend Framework** | FastAPI | 0.121.3 |
| **Template Engine** | Jinja2 | 3.1.6 |
| **HTTP Client** | HTTPX | 0.28.1 |
| **Session Management** | Starlette SessionMiddleware | 0.50.0 |
| **Data Validation** | Pydantic | 2.12.4 |
| **ASGI Server** | Uvicorn | 0.38.0 |
| **WSGI Server** | Gunicorn | 23.0.0 |
| **Python Version** | Python | 3.13 |

---

## 2. Environment Configuration

### 2.1 Environment Variables

Create the following environment variables in your deployment platform:

```env
# Session Configuration (REQUIRED)
SECRET_KEY=<generate-with-command-below>
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
APP_VERSION=2.0.0

# Server Configuration (Optional - has defaults)
HOST=0.0.0.0
PORT=8000
RELOAD=false

# Security (Optional - has default)
SSL_VERIFY=true
```

### Generate Secret Key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2.2 Configuration Files

**Required File**: `config/apikey.json` (not in version control)

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

**File Permissions** (if deploying outside Azure):
```bash
chmod 600 config/apikey.json
chmod 600 .env
```

**Company Logos**: Upload logos to `static/images/` directory

---

## 3. Deployment Process

### 3.1 Current Deployment: Azure App Service via GitHub Actions

**Platform**: Azure App Service
**CI/CD**: GitHub Actions
**Workflow File**: `.github/workflows/main_guideportal.yml`

#### Deployment Workflow

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

      - name: Install dependencies
        run: |
          python -m venv antenv
          source antenv/bin/activate
          pip install -r requirements.txt

      - name: Upload artifact
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
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: python-app

      - name: Deploy to Azure Web App
        uses: azure/webapps-deploy@v3
        with:
          app-name: 'guideportal'
          slot-name: 'Production'
          publish-profile: ${{ secrets.AZUREAPPSERVICE_PUBLISHPROFILE_* }}
```

#### Deployment Steps

1. **Trigger**: Code pushed to `main` branch triggers workflow
2. **Build**: Python 3.13 environment created, dependencies installed
3. **Package**: Application artifact uploaded (excluding virtual environment)
4. **Deploy**: Artifact deployed to Azure App Service via publish profile
5. **Build on Platform**: Oryx build engine handles compilation on Azure

#### Azure App Service Configuration

- **App Name**: `guideportal`
- **Deployment Slot**: `Production`
- **Build Engine**: Oryx (automatically enabled via `SCM_DO_BUILD_DURING_DEPLOYMENT=true`)
- **Authentication**: Publish profile stored in GitHub Secrets
- **Runtime**: Python 3.13
- **Server**: Gunicorn (production) or Uvicorn (development)

### 3.2 Azure App Service Settings

Configure in **Azure Portal → Configuration → Application Settings**:

1. Add all environment variables from Section 2.1
2. Ensure `SECRET_KEY` is properly generated (32+ character random string)
3. Set `DEBUG=false` for production
4. Configure `SCM_DO_BUILD_DURING_DEPLOYMENT=true` (usually automatic)

### 3.3 GitHub Secrets Configuration

**Required Secret**: `AZUREAPPSERVICE_PUBLISHPROFILE_*`

**How to Configure**:
1. Download publish profile from Azure Portal (App Service → Get publish profile)
2. Add to GitHub: Repository → Settings → Secrets and variables → Actions
3. Create new secret with the publish profile XML content

---

## 4. Network Requirements

### 4.1 Inbound Traffic

| Port | Protocol | Source | Purpose | Notes |
|------|----------|--------|---------|-------|
| 443 | HTTPS | Internet | Web traffic | Azure App Service handles SSL |
| 80 | HTTP | Internet | Redirects to HTTPS | Azure auto-redirects (platform level) |

**Azure App Service Notes**:
- SSL certificates managed by Azure
- Custom domain configuration in Azure Portal
- HTTPS automatically enforced at platform level

### 4.2 Outbound Traffic

| Destination | Protocol | Port | Purpose |
|-------------|----------|------|---------|
| api.tourcube.com | HTTPS | 443 | Production API calls |
| test-api.tourcube.com | HTTPS | 443 | Test API calls |

**Firewall Configuration**:
- Azure App Service allows outbound HTTPS by default
- No additional firewall rules needed for standard deployment

---

## 5. Post-Deployment Validation

### 5.1 Automated Tests

```bash
# 1. Health check endpoint
curl https://guideportal.azurewebsites.net/health
# Expected: {"status": "healthy", "version": "2.0.0"}

# 2. SSL/TLS verification
openssl s_client -connect guideportal.azurewebsites.net:443 -servername guideportal.azurewebsites.net
# Expected: Valid Azure SSL certificate, TLS 1.2 or higher

# 3. Root redirect
curl -I https://guideportal.azurewebsites.net/
# Expected: 302 redirect to /auth/login?company_code=WTGUIDE&mode=Test
```

### 5.2 Manual Tests

#### Test 1: Login Flow
1. Navigate to: `https://guideportal.azurewebsites.net/auth/login?company_code=WTGUIDE&mode=Production`
2. **Expected**: Branded login page with company logo and theme
3. Enter valid credentials
4. **Expected**: Redirect to `/guide/home` or `/vendor/home` based on user type

#### Test 2: Session Cookie
1. Open browser DevTools → Application → Cookies
2. Check cookie `guide_portal_session`
3. **Expected Attributes**:
   - `HttpOnly`: `true`
   - `Secure`: May be set by Azure (check in production)
   - `Max-Age`: `86400` (24 hours)

#### Test 3: Static Files
1. Navigate to: `https://guideportal.azurewebsites.net/static/css/dashlite.css`
2. **Expected**: CSS file loads successfully
3. Check logo: `https://guideportal.azurewebsites.net/static/images/logo.png`

#### Test 4: Company Configuration
1. Test with different company codes (if configured)
2. Verify different logos and themes load correctly
3. Test both Test and Production modes

---

## 6. Deployment Checklist

### Pre-Deployment

- [ ] **Environment Variables**
  - [ ] `SECRET_KEY` generated and configured in Azure App Settings
  - [ ] `DEBUG=false` for production
  - [ ] `SSL_VERIFY=true` for production
  - [ ] All other variables configured with appropriate values

- [ ] **Configuration Files**
  - [ ] `config/apikey.json` created with production API keys
  - [ ] All company logos uploaded to Azure file storage or `static/images/`
  - [ ] Verify JSON structure matches expected format

- [ ] **GitHub Configuration**
  - [ ] Publish profile secret configured in GitHub
  - [ ] Workflow file tested and working
  - [ ] Branch protection rules configured (if needed)

- [ ] **Azure App Service**
  - [ ] App Service created and configured
  - [ ] Python 3.13 runtime selected
  - [ ] Custom domain configured (if needed)
  - [ ] HTTPS enforced (automatic in Azure)
  - [ ] Application Insights enabled (recommended)

### Post-Deployment

- [ ] **Validation Tests**
  - [ ] Health check endpoint returns 200 OK
  - [ ] Login flow works for all user types
  - [ ] Session cookies properly configured
  - [ ] Static files load correctly
  - [ ] All company configurations work

- [ ] **Monitoring**
  - [ ] Application Insights configured and receiving data
  - [ ] Alerts configured for errors and downtime
  - [ ] Log retention policies configured

- [ ] **Security**
  - [ ] SSL certificate valid and trusted
  - [ ] HTTPS enforced (no HTTP access)
  - [ ] Session cookies secure
  - [ ] API keys not exposed in logs or errors

---

## 7. Troubleshooting

### Common Issues

#### Issue 1: Application Not Starting
**Symptoms**: Azure shows "Application Error"
**Causes**:
- Missing `SECRET_KEY` environment variable
- Missing or invalid `config/apikey.json`
- Python version mismatch

**Solutions**:
1. Check Azure App Service logs: Portal → Log stream
2. Verify all required environment variables are set
3. Ensure Python 3.13 runtime is selected
4. Check `requirements.txt` dependencies are correct

#### Issue 2: Login Fails
**Symptoms**: Login returns error or redirect loops
**Causes**:
- Invalid API key in `config/apikey.json`
- Wrong API URL (Test vs Production)
- Company code mismatch

**Solutions**:
1. Verify API key is correct for the mode (Test/Production)
2. Check company code exists in `apikey.json`
3. Test API connectivity: `curl -H "tc-api-key: YOUR_KEY" https://api.tourcube.com/...`

#### Issue 3: Static Files Not Loading
**Symptoms**: Missing CSS, images, or JavaScript
**Causes**:
- Incorrect static file path
- Files not included in deployment artifact

**Solutions**:
1. Verify `static/` directory is in deployment package
2. Check Azure App Service file structure via Kudu console
3. Ensure `app.mount("/static", ...)` is in `main.py`

#### Issue 4: Session Not Persisting
**Symptoms**: Users logged out on each request
**Causes**:
- `SECRET_KEY` changing between requests
- Session middleware not configured
- Cookie attributes blocking storage

**Solutions**:
1. Verify `SECRET_KEY` is set in Azure App Settings (not in code)
2. Check SessionMiddleware is added in `main.py`
3. Verify browser accepts cookies from domain

---

## 8. Rollback Procedure

### Via Azure Portal

1. Navigate to: Azure Portal → App Service → Deployment → Deployment Center
2. Select previous successful deployment
3. Click "Redeploy"

### Via GitHub Actions

1. Navigate to: GitHub → Actions → Workflows
2. Find last successful workflow run
3. Click "Re-run all jobs"

### Manual Rollback

```bash
# 1. Checkout previous version
git checkout <previous-commit-hash>

# 2. Push to main (triggers deployment)
git push origin HEAD:main --force
```

---

## 9. Maintenance

### Regular Tasks

**Daily**:
- Monitor Application Insights for errors
- Check Azure App Service health

**Weekly**:
- Review deployment logs
- Check disk usage and performance metrics

**Monthly**:
- Update Python dependencies: `pip list --outdated`
- Review and rotate API keys (if policy requires)
- Update SSL certificates (automatic in Azure)
- Security audit of configurations

### Updates and Patches

**Python Dependencies**:
```bash
# Update requirements.txt
pip list --outdated
pip install --upgrade <package-name>
pip freeze > requirements.txt

# Test locally, then push to trigger deployment
git add requirements.txt
git commit -m "Update dependencies"
git push origin main
```

**Configuration Changes**:
1. Update `config/apikey.json` or environment variables in Azure Portal
2. Restart App Service: Portal → Overview → Restart

---

## 10. Support and Escalation

### Log Access

**Azure App Service Logs**:
- Portal → Log stream (real-time)
- Portal → Kudu console → Log files
- Application Insights → Logs

**GitHub Actions Logs**:
- Repository → Actions → Select workflow run

### Key Contacts

| Role | Responsibility |
|------|----------------|
| **Development Team** | Application code, bug fixes |
| **Infrastructure Team** | Azure configuration, deployment |
| **Security Team** | Security reviews, incident response |
| **Tourcube API Support** | API issues, key rotation |

---

## Appendix A: Azure CLI Commands

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# View App Service configuration
az webapp config appsettings list \
  --name guideportal \
  --resource-group YOUR_RESOURCE_GROUP

# Update environment variable
az webapp config appsettings set \
  --name guideportal \
  --resource-group YOUR_RESOURCE_GROUP \
  --settings SECRET_KEY="your-new-key"

# Restart App Service
az webapp restart \
  --name guideportal \
  --resource-group YOUR_RESOURCE_GROUP

# View deployment logs
az webapp log tail \
  --name guideportal \
  --resource-group YOUR_RESOURCE_GROUP
```

---

## Appendix B: File Structure

```
Deployment Package Structure:
├── app/
│   ├── main.py
│   ├── config.py
│   ├── routes/
│   ├── services/
│   └── models/
├── config/
│   └── apikey.json           # Must be created manually (not in git)
├── static/
│   ├── css/
│   ├── js/
│   ├── fonts/
│   └── images/               # Company logos here
├── templates/
│   ├── base.html
│   ├── layouts/
│   ├── components/
│   └── pages/
├── requirements.txt
├── .env                      # Azure uses App Settings instead
└── runtime.txt               # Optional: specify Python version
```

---

**End of Document**

*For detailed security implementation, see `SECURITY_IMPLEMENTATION_OVERVIEW.md`*
*For development setup, see `README.md` and `QUICKSTART.md`*
