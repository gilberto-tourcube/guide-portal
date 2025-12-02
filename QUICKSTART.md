# Quick Start Guide - Tourcube Guide Portal

## What's Been Implemented

### ✅ Authentication System (Complete)
- **Multi-company login** with dynamic branding
- **Dynamic skin theming** per company
- **Password visibility toggle** and loading spinners
- **Forgot username** functionality (fully implemented)
- **Forgot password** UI (backend pending user lookup)
- **Session management** with encrypted cookies
- Support for **Guide and Vendor** users

### ✅ Guide Homepage (Complete)
- **Three-tab interface** (Future Trips | Past Trips | Forms Due)
- **Responsive DashLite v3.3** Bootstrap 5 UI
- **FastAPI backend** with async API calls
- **Type-safe** Pydantic models
- **Business logic** preserved from legacy WebDev system
- Complete documentation

## Quick Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your values
nano .env  # or use your preferred editor
```

Required values in `.env`:
```env
# Company defaults
COMPANY_CODE=WTGUIDE
MODE=Test

# API Configuration (fallback)
API_BASE_URL=https://api.tourcube.com
API_KEY=your_api_key_here
API_TIMEOUT=30

# Session security
SECRET_KEY=generate_using_openssl_rand_hex_32
SESSION_COOKIE_NAME=guide_portal_session
SESSION_MAX_AGE=86400

# SSL verification
SSL_VERIFY=true
```

Generate a secret key:
```bash
openssl rand -hex 32
```

### 3. Create Company Configuration

Create `config/apikey.json` with your company settings:

```json
{
  "TourcubeAPIKey": [
    {
      "CompanyID": "WTGUIDE",
      "Logo": "wilderness-travel-logo.png",
      "TourcubeOnline": true,
      "SkinName": "theme-bluelite",
      "Test": "YOUR_TEST_API_KEY",
      "TestURL": "https://test-api.tourcube.com",
      "Production": "YOUR_PRODUCTION_API_KEY",
      "ProductionURL": "https://api.tourcube.com"
    }
  ]
}
```

**Available Skins**:
- `theme-bluelite` - Light blue theme (default)
- `theme-egyptian` - Egyptian color palette
- `theme-green` - Green theme
- `theme-purple` - Purple theme
- `theme-red` - Red theme

### 4. Add Company Logos

Place company logos in `static/images/`:
- Company logo: `static/images/wilderness-travel-logo.png`
- Default logo: `static/images/logo.png`
- Favicon: `static/images/favicon.ico`

### 5. Run the Application

```bash
uvicorn app.main:app --reload
```

The application will be available at:
- **Login Page**: http://localhost:8000/login?company_code=WTGUIDE&mode=Test
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Testing the Implementation

### Login Flow Test

1. **Access Login Page**:
   ```
   http://localhost:8000/login?company_code=WTGUIDE&mode=Test
   ```

2. **Verify**:
   - Company logo displays correctly
   - Theme skin loads (check background colors)
   - Username field is autofocused
   - Password field has eye icon for visibility toggle
   - "Forgot Password?" link works
   - "Forgot Username?" footer link works

3. **Submit Credentials**:
   - Enter valid username and password
   - Watch for loading spinner
   - Button disables during submission

4. **After Login**:
   - Guides (Type 1) → Redirected to `/guide/home`
   - Vendors (Type 2) → Redirected to `/vendor/home`
   - Session created with user data

### Guide Homepage Test

After successful login as a Guide:

1. **Future Trips Tab**:
   - [ ] Tab displays and loads data
   - [ ] Trip rows are clickable
   - [ ] Dates formatted correctly
   - [ ] Group sizes display

2. **Past Trips Tab**:
   - [ ] Tab displays completed trips
   - [ ] Data matches API response

3. **Forms Due Tab**:
   - [ ] Forms display with correct colors:
     - 🟢 Green = Completed and editable
     - 🔵 Blue = Pending completion
     - 🔴 Red = Overdue
     - ⚫ Gray = Disabled
   - [ ] Pending forms counter accurate
   - [ ] Contact info displays correctly

4. **Navigation**:
   - [ ] Sidebar navigation works
   - [ ] User dropdown displays
   - [ ] Logout functionality works

5. **Responsive Design**:
   - [ ] Mobile view works correctly
   - [ ] Sidebar collapses on mobile
   - [ ] All icons display

### Multi-Company Test

Test with different company configurations:

```bash
# Company A with blue theme
http://localhost:8000/login?company_code=WTGUIDE&mode=Test

# Company B with different theme (if configured)
http://localhost:8000/login?company_code=OTHER&mode=Production
```

Verify:
- [ ] Different logos display
- [ ] Different theme colors load
- [ ] Correct API endpoints used

## Project Structure

```
guide-portal/
├── .claude/
│   └── builder-context-chat.md    # Development context
├── app/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Multi-company settings
│   ├── routes/
│   │   ├── auth.py               # Login, logout, forgot password/username
│   │   └── guide.py              # Guide homepage
│   ├── services/
│   │   ├── auth_service.py       # Authentication logic
│   │   └── guide_service.py      # Guide business logic
│   └── models/
│       └── schemas.py            # Pydantic models
├── config/
│   └── apikey.json               # Company configurations (git-ignored)
├── templates/
│   ├── base.html                 # Base with dynamic skin support
│   ├── layouts/
│   │   ├── auth.html            # Centered auth layout
│   │   └── dashboard.html       # Dashboard layout
│   ├── components/
│   │   ├── navbar.html          # Top navigation
│   │   └── sidebar.html         # Side navigation
│   └── pages/
│       ├── login.html           # Login page
│       ├── forgot_password.html # Password recovery
│       ├── forgot_username.html # Username recovery
│       └── guide_home.html      # Guide homepage
├── static/
│   ├── css/
│   │   └── skins/               # DashLite theme variants
│   ├── js/
│   ├── fonts/
│   └── images/                  # Company logos
└── docs/                        # Documentation (git-ignored)
```

## API Endpoints

### External Tourcube API (Consumed)

1. **Portal Login**
   ```
   POST /tourcube/guidePortal/login
   Headers: tc-api-key
   Body: {"portalUserName": "...", "portalPassword": "..."}
   Response: {"LoginFailed": false, "Type": 1, "GuideClientID": 123, ...}
   ```

2. **Get Guide Homepage**
   ```
   GET /tourcube/guidePortal/getGuideHomepage/{guideID}
   Returns: guide info, future trips, past trips
   ```

3. **Get Guide Forms**
   ```
   GET /tourcube/guidePortal/getGuideForms/{guideID}/0
   Returns: list of forms
   ```

4. **Forgot Username**
   ```
   GET /tourcube/guidePortal/forgotUserName/{email}
   Sends: username reminder email
   ```

### Internal Application Routes

- **Auth**: `/`, `/login`, `/logout`, `/forgot-password`, `/forgot-username`
- **Guide**: `/guide/home`
- **System**: `/health`, `/docs`

## Troubleshooting

### Port Already in Use
```bash
# Use a different port
uvicorn app.main:app --reload --port 8001
```

### Module Not Found Errors
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### Static Files Not Loading
Check that you're using `url_for()` in templates:
```jinja2
<!-- Correct -->
<link rel="stylesheet" href="{{ url_for('static', path='/css/dashlite.css') }}">

<!-- Wrong -->
<link rel="stylesheet" href="/static/css/dashlite.css">
```

### API Connection Errors
1. Check `config/apikey.json` exists and has correct API keys
2. Verify API is accessible from your network
3. Check `SSL_VERIFY` setting in `.env`
4. Review logs for specific error messages

### Skin Not Loading
1. Verify `SkinName` in `config/apikey.json` matches a file in `static/css/skins/`
2. Check browser console for 404 errors
3. Ensure skin CSS files were copied from DashLite template

### Session/Login Issues
1. Verify `SECRET_KEY` is set in `.env`
2. Check session cookie settings
3. Clear browser cookies and try again
4. Check that SessionMiddleware is configured in `app/main.py`

### Company Configuration Not Found
```bash
# Error: Company 'WTGUIDE' not found
# Solution: Check config/apikey.json exists and CompanyID matches

cat config/apikey.json  # Verify file contents
```

## Development Tips

### Auto-reload on Changes
The `--reload` flag watches for file changes:
```bash
uvicorn app.main:app --reload
```

Changes to these files trigger reload:
- Python files (`.py`)
- Template files (`.html`)
- Does **not** watch: static files (CSS/JS), config files

### Debug Mode
Enable debug mode in `.env`:
```env
DEBUG=true
```

This provides:
- Detailed error pages
- Stack traces in responses
- Additional logging

### View Logs
FastAPI logs appear in the terminal where uvicorn is running:
```bash
INFO:     127.0.0.1:54321 - "GET /login HTTP/1.1" 200 OK
INFO:     127.0.0.1:54321 - "POST /login HTTP/1.1" 303 See Other
```

### API Documentation
FastAPI automatically generates interactive API docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Testing Different Companies
Add multiple companies to `config/apikey.json`:
```json
{
  "TourcubeAPIKey": [
    {
      "CompanyID": "WTGUIDE",
      "SkinName": "theme-bluelite",
      ...
    },
    {
      "CompanyID": "COMPANY2",
      "SkinName": "theme-green",
      ...
    }
  ]
}
```

Then test: `http://localhost:8000/login?company_code=COMPANY2&mode=Test`

## Next Steps

### Immediate TODOs
1. ✅ ~~Implement Authentication~~ (Complete)
2. ✅ ~~Create login page~~ (Complete)
3. ✅ ~~Add session management~~ (Complete)
4. [ ] **Add real company logos** to `static/images/`
5. [ ] **Test with production API** credentials
6. [ ] **Create vendor homepage** placeholder

### Short-term Development
1. **Authentication Middleware**
   - Create decorator for protected routes
   - Add automatic redirect to login
   - Implement session refresh

2. **Error Pages**
   - Create 404 not found page
   - Create 500 error page
   - Add custom error handlers

3. **Forgot Password**
   - Implement user lookup logic
   - Complete send_temp_password functionality

### Future Development
1. **Trip Details Page** (Page_DeparturePage from legacy)
2. **Form Submission/Editing**
3. **User Profile Page**
4. **Additional legacy pages migration**

## Getting Help

### Documentation
- **Project README**: [README.md](README.md)
- **Builder Context**: [.claude/builder-context-chat.md](.claude/builder-context-chat.md)
- **Implementation Details**:
  - Login: `docs/current-project/LOGIN_IMPLEMENTATION.md` (git-ignored)
  - Guide Home: `docs/current-project/GUIDEHOMEPAGE_IMPLEMENTATION.md` (git-ignored)
- **DashLite Docs**: `docs/template/dashlite-v3.3.0/` (git-ignored)

### External Resources
- **FastAPI**: https://fastapi.tiangolo.com/
- **Jinja2**: https://jinja.palletsprojects.com/
- **Bootstrap 5**: https://getbootstrap.com/docs/5.3/
- **Pydantic**: https://docs.pydantic.dev/

## Status

**Current Version**: 1.0.0
**Last Updated**: 2025-11-19
**Status**: Authentication and Guide Homepage fully implemented

### Feature Completion
- ✅ Multi-company authentication system
- ✅ Dynamic theming system
- ✅ Guide homepage with trips and forms
- ✅ Session management
- ✅ Forgot username functionality
- 🚧 Forgot password (UI complete, backend pending)
- 🚧 Vendor homepage (redirect exists, page pending)
- 📝 Trip details page (not started)

---

**Ready to run!** Follow the steps above and you'll have the application running with full authentication and guide features.
