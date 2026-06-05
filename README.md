# Tourcube Guide Portal

A modern web portal built with FastAPI and Jinja2, designed for tour guides and vendors management using the DashLite v3.3 Bootstrap 5 admin template.

## 📋 Overview

The Tourcube Guide Portal is a web application that consumes external APIs to provide a comprehensive interface for managing tour guides, vendors, bookings, and related operations. This project is a modernization of a legacy WebDev system, built with clean architecture principles and modern web technologies.

## ✨ Current Implementation Status

### ✅ Completed Features

#### Authentication System
- Multi-company login support with dynamic branding
- Dynamic DashLite skin theming per company (7 themes available)
- Separate routes for login, logout, forgot password, and forgot username
- Session-based authentication with encrypted cookies
- Support for both Guide (Type 1) and Vendor (Type 2) users
- Password visibility toggle and loading spinners
- Improved error messaging
- Forgot username functionality with email lookup

#### Guide Features
- **Guide Homepage**: Three-tab interface (Future Trips | Past Trips | Forms Due)
- **Trip Details Page**: Complete trip information with departure list
- **Trip Departure Page**: Detailed departure information with passenger list
- **Client Details Page**: Comprehensive client information with trip context
- Responsive data tables with mobile optimization
- Smart form status system with color-coded buttons
- Pending forms counter
- Business logic from legacy system preserved

#### Vendor Features
- **Vendor Homepage**: Two-tab interface (Future Trips | Past Trips)
- Responsive trip tables with clickable trip/departure links
- Full integration with resource pages (trips, departures, clients)

#### Resource-Based Routing Architecture ✨ **NEW**
- RESTful resource routes without user-type prefixes
- Generic routes: `/trip/{id}`, `/departure/{id}`, `/client/{id}`
- User-specific routes only for homepages: `/guide/home`, `/vendor/home`
- Access control in service layer (not in routes)
- Eliminates code duplication
- Scalable for new user types

#### Dynamic Navigation
- **Dynamic Breadcrumbs**: Automatically adjust based on user role (Guide/Vendor)
- Context-aware navigation with trip/departure information
- Consistent navigation patterns across all pages

### 📝 Pending
- Forgot password backend implementation
- Authentication middleware/decorators
- Error pages (404, 500)
- Forms Due tab for vendor homepage (if needed)
- Additional legacy page migrations

## 🏗️ Architecture

### Tech Stack

- **Backend Framework**: FastAPI 0.109+
- **Template Engine**: Jinja2 3.1+
- **Frontend Theme**: DashLite v3.3 (Bootstrap 5)
- **HTTP Client**: HTTPX (async)
- **Configuration**: Pydantic Settings
- **Session Management**: Starlette SessionMiddleware
- **Python Version**: 3.11+

### Key Architectural Decisions

1. **No Database**: Stateless application consuming external APIs only
2. **Multi-Company Architecture**: Dynamic configuration per company (logos, skins, API credentials)
3. **Resource-Based Routing**: URLs represent resources (trips, departures, clients), not user types
4. **Template-Based Rendering**: Server-side rendering with Jinja2 for optimal SEO
5. **Async-First**: All API calls use async/await for better performance
6. **Clean Separation**: Clear separation between routes, services, and presentation layers
7. **Dynamic Theming**: Company-specific DashLite skins loaded at runtime
8. **Access Control in Services**: Permission logic in service layer, not routes

## 📁 Project Structure

```
guide-portal/
├── .claude/                       # Claude Code context and session history
│   └── builder-context-chat.md   # Development session context
│
├── app/                           # Application core
│   ├── __init__.py
│   ├── main.py                    # FastAPI application setup
│   ├── config.py                  # Settings with multi-company support
│   ├── routes/                    # Route handlers (controllers)
│   │   ├── __init__.py
│   │   ├── auth.py               # Authentication routes
│   │   ├── guide.py              # Guide-specific routes (/guide/home)
│   │   ├── vendor.py             # Vendor-specific routes (/vendor/home)
│   │   └── resources.py          # Generic resource routes (trips, departures, clients)
│   ├── services/                  # Business logic and API clients
│   │   ├── __init__.py
│   │   ├── api_client.py         # HTTP client wrapper
│   │   ├── auth_service.py       # Authentication service
│   │   ├── guide_service.py      # Guide business logic
│   │   └── vendor_service.py     # Vendor business logic
│   └── models/                    # Pydantic models (DTOs and schemas)
│       ├── __init__.py
│       └── schemas.py            # Request/Response models
│
├── config/                        # Configuration files (git-ignored)
│   ├── apikey.json               # Multi-company API credentials
│   └── .gitkeep
│
├── static/                        # Static assets
│   ├── css/
│   │   ├── dashlite.css         # DashLite core styles
│   │   ├── theme.css            # Theme variables
│   │   ├── custom.css           # Custom styles
│   │   └── skins/               # DashLite skin variants
│   │       ├── theme-bluelite.css  # Default (#29347a)
│   │       ├── theme-darkblue.css  # (#021628)
│   │       ├── theme-egyptian.css  # (#02274d)
│   │       ├── theme-purple.css    # (#36206a)
│   │       ├── theme-green.css     # (#064936)
│   │       ├── theme-red.css       # (#5f2525)
│   │       └── theme-blue.css      # (#0a2d6c)
│   ├── js/
│   │   ├── bundle.js            # DashLite core scripts
│   │   └── scripts.js           # DashLite additional scripts
│   ├── fonts/                    # NioIcon font files
│   └── images/                   # Company logos and images
│       ├── logo.png
│       └── favicon.ico
│
├── templates/                     # Jinja2 templates
│   ├── base.html                 # Base layout with dynamic skin support
│   ├── layouts/
│   │   ├── dashboard.html       # Dashboard layout (with sidebar)
│   │   └── auth.html            # Authentication layout (centered)
│   ├── components/
│   │   ├── navbar.html          # Top navigation bar
│   │   └── sidebar.html         # Side navigation menu
│   └── pages/
│       ├── guide_home.html      # Guide homepage (3 tabs)
│       ├── vendor_home.html     # Vendor homepage (2 tabs)
│       ├── trip.html            # Trip details page
│       ├── trip_departure.html  # Trip departure details
│       ├── client.html          # Client details page
│       ├── login.html           # Login page
│       ├── forgot_password.html # Password recovery
│       └── forgot_username.html # Username recovery
│
├── docs/                          # Documentation (git-ignored)
│   ├── template/                 # DashLite template documentation
│   ├── legacy-project/           # Legacy WebDev system docs
│   └── current-project/          # Current implementation docs
│       ├── GUIDEHOMEPAGE_IMPLEMENTATION.md
│       └── LOGIN_IMPLEMENTATION.md
│
├── .env                          # Environment variables (git-ignored)
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── README.md                     # This file
└── QUICKSTART.md                 # Quick start guide
```

## 🎯 Layer Responsibilities

### Routes Layer (`app/routes/`)
- Handle HTTP requests and responses
- Request validation (via Pydantic)
- Call service layer for business logic
- Render templates with data
- Session management
- Error handling and redirects
- **Resource Routes** (`resources.py`): Generic routes for shared resources (trips, departures, clients)
- **User Routes** (`guide.py`, `vendor.py`): User-specific routes (homepages only)

### Services Layer (`app/services/`)
- External API communication
- Business logic implementation
- Data transformation and validation
- Error handling and retry logic
- Response parsing

### Models Layer (`app/models/`)
- Pydantic models for request/response validation
- Type-safe data structures
- Field validation and aliases
- API request/response schemas

### Templates Layer (`templates/`)
- HTML presentation with Jinja2
- Template inheritance hierarchy
- Reusable components
- Dynamic content rendering

## 🔧 Configuration

### Multi-Company Configuration

The application supports multiple companies with different configurations via `config/apikey.json` (git-ignored, restored from the `APIKEY_JSON` secret in CI):

- Keys/URLs: `Test`/`Production` and `TestURL`/`ProductionURL`
- Branding: `Logo`, `SkinName`, `TourcubeOnline`
- **Domain mapping**: `TestDomains` and `ProductionDomains` let you resolve company/mode from the request host when `company_code`/`mode` are not in the query. Resolution order: query params > host mapping > defaults (`COMPANY_CODE`/`MODE`).
- Distribution: `config/apikey.json` is git-ignored and reconstructed in CI from the `APIKEY_JSON` secret (see `.github/workflows/main_guideportal.yml`).

### Environment Variables

Create a `.env` file in the root directory:

```env
# API Configuration (fallback defaults)
API_BASE_URL=https://api.tourcube.com
API_KEY=your_api_key_here
API_TIMEOUT=30

# Company Configuration
COMPANY_CODE=WT
MODE=Test

# Application Settings
DEBUG=false
APP_NAME=Tourcube Guide Portal
APP_VERSION=1.0.0

# Server Configuration
HOST=0.0.0.0
PORT=8000
RELOAD=false

# Session Configuration
SECRET_KEY=generate_with_openssl_rand_hex_32
SESSION_COOKIE_NAME=guide_portal_session
SESSION_MAX_AGE=86400

# Security
SSL_VERIFY=true
```

Generate a secure secret key:
```bash
openssl rand -hex 32
```

## 🚀 Getting Started

See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions.

### Quick Start

```bash
# 1. Clone and navigate
git clone <repository-url>
cd guide-portal

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 5. Create company configuration
# Create config/apikey.json with your company settings

# 6. Run application
uvicorn app.main:app --reload

# 7. Access application
# Login: http://localhost:8000/login?company_code=WT&mode=Test
# API Docs: http://localhost:8000/docs
```

## 📦 Dependencies

### Core Dependencies
```
fastapi==0.109.0          # Web framework
uvicorn[standard]==0.27.0 # ASGI server
jinja2==3.1.3             # Template engine
httpx==0.26.0             # Async HTTP client
pydantic==2.5.0           # Data validation
pydantic-settings==2.1.0  # Settings management
python-dotenv==1.0.0      # Environment variables
itsdangerous==2.1.2       # Session encryption
```

## 🎨 Dynamic Theming System

The application supports company-specific DashLite themes via the `SkinName` configuration:

### Available Skins
- `theme-bluelite` - Light blue theme (Default - #29347a)
- `theme-darkblue` - Dark blue theme (#021628)
- `theme-egyptian` - Egyptian color palette (#02274d)
- `theme-purple` - Purple theme (#36206a)
- `theme-green` - Green theme (#064936)
- `theme-red` - Red theme (#5f2525)
- `theme-blue` - Blue theme (#0a2d6c)

### How It Works

1. Company configuration specifies `SkinName` in `config/apikey.json`
2. Login page receives `company_code` query parameter
3. System loads company config and passes `skin_name` to template
4. `base.html` dynamically includes the appropriate skin CSS
5. Each page inherits the company-specific theme

## 🔐 Authentication Flow

```
User → /login?company_code=WT&mode=Test
  ↓
Load company config (logo, skin, API credentials)
  ↓
Render login page with company branding
  ↓
User submits credentials
  ↓
POST /tourcube/guidePortal/login via auth_service
  ↓
API returns Type (1=Guide, 2=Vendor) + user data
  ↓
Create encrypted session
  ↓
Redirect: Type 1 → /guide/home | Type 2 → /vendor/home
```

### Session Data
```python
session["authenticated"] = True
session["user_type"] = 1 or 2
session["company_code"] = "WT"
session["mode"] = "Test" or "Production"

# For Guides (Type 1):
session["guide_id"]
session["guide_first_name"]
session["guide_last_name"]
session["guide_email"]

# For Vendors (Type 2):
session["vendor_id"]
session["vendor_name"]
```

## 🏛️ Routing Architecture

### Resource-Based Routing (RESTful Design)

The application follows a **resource-based routing architecture** instead of user-based routes:

#### ✅ Current Architecture (Resource-Based)
```
# User-specific routes (different homepages)
/guide/home          → Guide homepage
/vendor/home         → Vendor homepage

# Resource routes (shared by all user types)
/trip/{id}           → Trip details page (guides + vendors)
/departure/{id}      → Departure details page (guides + vendors)
/client/{id}         → Client details page (guides + vendors)
```

#### ❌ Previous Architecture (User-Based - Rejected)
```
/guide/home          → Guide homepage
/guide/trip/{id}     → Trip page (guides only) - DUPLICATION!
/guide/departure/{id} → Departure page (guides only) - DUPLICATION!

/vendor/home         → Vendor homepage
/vendor/trip/{id}    → Trip page (vendors only) - DUPLICATION!
/vendor/departure/{id} → Departure page (vendors only) - DUPLICATION!
```

#### Architectural Principles
1. **Routes = Resources, not Users**: URLs represent entities (trips, departures, clients), not who accesses them
2. **Access Control in Service Layer**: Permission logic is in services, not routes
3. **DRY (Don't Repeat Yourself)**: One route per resource, not one per user type
4. **Scalability**: Adding new user types doesn't require duplicating all routes

#### Implementation
- **Generic Routes**: `app/routes/resources.py` contains `/trip/{id}`, `/departure/{id}`, `/client/{id}`
- **User-Specific Routes**: `app/routes/guide.py` and `app/routes/vendor.py` contain only homepage routes
- **Authentication**: `user_id = request.session.get("guide_id") or request.session.get("vendor_id")`
- **Service Routing**: Calls `guide_service` or `vendor_service` as needed based on user type

## 🌐 API Endpoints

### Authentication Routes
- `GET /` - Redirect to login
- `GET /login` - Display login form
- `POST /login` - Process login
- `GET /logout` - Clear session
- `GET /forgot-password` - Password recovery form
- `POST /forgot-password` - Process password recovery (placeholder)
- `GET /forgot-username` - Username recovery form
- `POST /forgot-username` - Send username reminder

### Guide Routes
- `GET /guide/home` - Guide homepage (requires authentication)

### Vendor Routes
- `GET /vendor/home` - Vendor homepage (requires authentication)

### Resource Routes (Accessible by Guides and Vendors)
- `GET /trip/{id}` - Trip details page
- `GET /departure/{id}` - Trip departure details page
- `GET /client/{id}` - Client details page

### System Routes
- `GET /health` - Health check endpoint

### External API Endpoints Consumed

```bash
# Authentication
POST /tourcube/guidePortal/login
GET  /tourcube/guidePortal/forgotUserName/{email}

# Guide Endpoints
GET  /tourcube/guidePortal/getGuideHomepage/{guideID}
GET  /tourcube/guidePortal/getGuideForms/{guideID}/{tripDepartureID}

# Vendor Endpoints
GET  /tourcube/guidePortal/getVendorHomepage/{vendorID}

# Resource Endpoints (accessible by both guides and vendors)
GET  /tourcube/guidePortal/getDeparturePage/{tripDepartureID}
GET  /tourcube/guidePortal/getTripPage/{tripID}
GET  /tourcube/guidePortal/getClientPage/{clientID}
```

## 🔄 Development Workflow

### Adding a New Feature

1. **Define routes** in `app/routes/`
2. **Create service methods** in `app/services/`
3. **Define Pydantic models** in `app/models/schemas.py`
4. **Create templates** in `templates/pages/`
5. **Add static assets** if needed
6. **Update documentation**

### Code Style

- Follow PEP 8 guidelines
- Use type hints for all functions
- Use Pydantic for data validation
- Keep functions focused and small
- Document complex business logic

## 📚 Documentation

- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Builder Context**: [.claude/builder-context-chat.md](.claude/builder-context-chat.md)
- **Implementation Docs**: `docs/current-project/` (git-ignored)
- **Legacy Reference**: `docs/legacy-project/` (git-ignored)
- **Template Docs**: `docs/template/` (git-ignored)

## 🧪 Testing

### Manual Testing

```bash
# Start application
uvicorn app.main:app --reload

# Test login
http://localhost:8000/login?company_code=WT&mode=Test

# Test different company/mode
http://localhost:8000/login?company_code=OTHER&mode=Production
```

### Automated Testing (Future)
```bash
pytest
pytest --cov=app tests/
```

## 🚢 Deployment

### Production Checklist
- [ ] Set `DEBUG=false` in production `.env`
- [ ] Generate secure `SECRET_KEY`
- [ ] Configure `config/apikey.json` with production API keys
- [ ] Set `SSL_VERIFY=true`
- [ ] Add actual company logos to `static/images/`
- [ ] Configure reverse proxy (nginx/Apache)
- [ ] Set up HTTPS certificates
- [ ] Configure session security settings
- [ ] Set appropriate `SESSION_MAX_AGE`

### Docker Deployment
```bash
# Build
docker build -t guide-portal .

# Run
docker run -p 8000:8000 --env-file .env guide-portal
```

## 🔒 Security Considerations

### Implemented
✅ Encrypted session cookies
✅ HTTPS enforcement (SSL_VERIFY)
✅ API keys stored in git-ignored config
✅ Password field masking
✅ CSRF protection via SessionMiddleware
✅ Input validation via Pydantic

### Future Enhancements
- [ ] Rate limiting
- [ ] Account lockout after failed attempts
- [ ] MFA (Multi-Factor Authentication)
- [ ] Password complexity requirements
- [ ] Audit logging

## 🗺️ Roadmap

### Phase 1: Core Authentication ✅
- ✅ Login system
- ✅ Multi-company support
- ✅ Dynamic theming (7 skins)
- ✅ Session management
- ✅ Forgot username functionality

### Phase 2: Guide Features ✅
- ✅ Guide homepage (3 tabs: Future Trips, Past Trips, Forms Due)
- ✅ Trip details page
- ✅ Trip departure details page
- ✅ Client details page
- ✅ Forms management system
- ✅ Responsive tables with mobile optimization

### Phase 3: Vendor Features ✅
- ✅ Vendor homepage (2 tabs: Future Trips, Past Trips)
- ✅ Resource-based routing architecture
- ✅ Dynamic breadcrumb navigation
- ✅ Full integration with resource pages

### Phase 4: Enhanced Features 🚧
- [ ] Forgot password backend implementation
- [ ] Authentication middleware/decorators
- [ ] Error pages (404, 500, 403)
- [ ] Forms Due tab for vendors (if needed)
- [ ] Form submission/editing functionality
- [ ] User profile page

### Phase 5: Complete Migration 📝
- [ ] All remaining legacy pages migrated
- [ ] Full feature parity with legacy system
- [ ] Performance optimization (caching, bundle size)
- [ ] Comprehensive testing (unit, integration, E2E)
- [ ] Monitoring and logging implementation

## 🤝 Contributing

1. Follow project structure guidelines
2. Maintain code quality standards
3. Update documentation for features
4. Test thoroughly before submitting
5. Update `.claude/builder-context-chat.md` with implementation notes

## 📄 License

[Your License Here]

## 👥 Team

- **Project Lead**: [Name]
- **Backend Developer**: [Name]
- **Frontend Developer**: [Name]

## 📞 Support

For questions or issues:
- Documentation: See `QUICKSTART.md` and `.claude/builder-context-chat.md`
- API Docs: http://localhost:8000/docs (when running)

---

## 📊 Project Metrics

- **Backend Files**: 11 core files (routes, services, models)
- **Frontend Templates**: 13 templates (layouts, components, pages)
- **Available Themes**: 7 DashLite skins
- **Completed Features**: 20+ features across authentication, guide, vendor, and resource pages
- **Lines of Code**: ~2500+ (backend) + ~2000+ (templates)
- **Architecture**: Resource-based RESTful routing

---

**Version**: 2.0.0
**Last Updated**: 2025-11-28
**Status**: ✅ Multi-User Portal (Guides + Vendors) with Resource-Based Architecture
**Branch**: v0.20251126
