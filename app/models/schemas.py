"""Pydantic models for request/response validation and data transfer"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, field_validator


# ============================================================================
# Guide Homepage Models
# ============================================================================

class TripSummary(BaseModel):
    """Model for a trip summary in the Future/Past trips tables"""
    trip_departure_id: Optional[int] = Field(None, description="Unique trip departure ID")
    trip_id: Optional[int] = Field(None, description="Trip ID for linking to trip page")
    tour_name: str = Field(..., description="Name of the tour")
    dates: str = Field(..., description="Date range string (e.g., 'January 1-16, 2026')")
    departure_date: Optional[date] = Field(None, description="Parsed departure date")
    return_date: Optional[date] = Field(None, description="Parsed return date")
    group_size: Optional[int] = Field(None, description="Number of travelers")
    trip_leaders: Optional[str] = Field(None, description="Trip leaders/guides names")
    dev_name: Optional[str] = Field(None, description="Trip developer name")
    ops_name: Optional[str] = Field(None, description="Operations contact name / Area Manager")

    class Config:
        json_schema_extra = {
            "example": {
                "trip_departure_id": 12345,
                "tour_name": "European Adventure",
                "dates": "June 15-25, 2024",
                "departure_date": "2024-06-15",
                "return_date": "2024-06-25",
                "group_size": 25,
                "dev_name": "John Developer",
                "ops_name": "Jane Operations"
            }
        }


class FormContact(BaseModel):
    """Contact information for form-related questions"""
    name: str = Field(..., description="Contact person name")
    email: str = Field(..., description="Contact email address")
    phone: Optional[str] = Field(None, description="Contact phone number")


class FormStatus(BaseModel):
    """Calculated status for a guide form"""
    status: str = Field(..., description="Status: pending, completed, expired, or disabled")
    button_text: str = Field(..., description="Text to display on button")
    button_class: str = Field(..., description="CSS class for button styling")
    is_clickable: bool = Field(..., description="Whether the form can be accessed")
    url: Optional[str] = Field(None, description="URL to form if clickable")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "pending",
                "button_text": "Complete Form",
                "button_class": "btn-form-pending",
                "is_clickable": True,
                "url": "https://example.com/forms/123"
            }
        }


class GuideForm(BaseModel):
    """Model for a guide form in the Forms Due section"""
    form_id: Optional[str] = Field(None, description="Unique form ID (can be hash)")
    form_name: str = Field(..., description="Name of the form")
    description: Optional[str] = Field(None, description="Form description")
    trip_info: Optional[str] = Field(None, description="Trip information")
    due_date: Optional[date] = Field(None, description="Form due date")
    departure_date: Optional[date] = Field(None, description="Trip departure date")
    received: bool = Field(False, description="Whether form has been submitted")
    required: bool = Field(False, description="Whether form is required")
    editable_after_submit: bool = Field(False, description="Can be edited after submission")
    url: str = Field(..., description="URL to access the form")
    pdf_url: Optional[str] = Field(None, description="URL to PDF version")
    form_type: Optional[str] = Field(None, description="Type of form (e.g., Evaluation)")

    # Contact information
    ops_name: Optional[str] = Field(None, description="Operations contact name")
    ops_email: Optional[str] = Field(None, description="Operations contact email")
    ops_phone: Optional[str] = Field(None, description="Operations contact phone")
    dev_name: Optional[str] = Field(None, description="Developer contact name")
    dev_email: Optional[str] = Field(None, description="Developer contact email")
    dev_phone: Optional[str] = Field(None, description="Developer contact phone")

    # Legacy support - contact object built from ops/dev fields
    contact: Optional[FormContact] = Field(None, description="Contact for questions")

    # Calculated fields (populated by service layer)
    status: Optional[FormStatus] = Field(None, description="Calculated form status")

    class Config:
        json_schema_extra = {
            "example": {
                "form_id": "BCC02DADB52BABF456F765307D744FB6",
                "form_name": "Travel Insurance Form",
                "description": "Required travel insurance information",
                "trip_info": "European Adventure - June 15, 2024",
                "due_date": "2024-05-30",
                "departure_date": "2024-06-15",
                "received": False,
                "required": True,
                "editable_after_submit": True,
                "url": "https://example.com/forms/789",
                "pdf_url": "https://example.com/forms/789.pdf",
                "form_type": "Evaluation",
                "ops_name": "Jane Operations",
                "ops_email": "ops@example.com",
                "contact": {
                    "name": "Operations Team",
                    "email": "operations@tourcube.com"
                }
            }
        }


class GuideHomepageData(BaseModel):
    """Complete data for the guide homepage"""
    guide_id: int = Field(..., description="Guide's unique ID")
    guide_name: str = Field(..., description="Guide's full name")
    guide_image: Optional[HttpUrl] = Field(None, description="URL to guide's profile image")
    future_trips: List[TripSummary] = Field(default_factory=list, description="List of upcoming trips")
    past_trips: List[TripSummary] = Field(default_factory=list, description="List of completed trips")
    forms: List[GuideForm] = Field(default_factory=list, description="List of forms requiring attention")
    forms_pending_count: int = Field(0, description="Number of incomplete forms")

    class Config:
        json_schema_extra = {
            "example": {
                "guide_id": 123,
                "guide_name": "John Smith",
                "guide_image": "https://example.com/images/guide123.jpg",
                "future_trips": [
                    {
                        "trip_departure_id": 12345,
                        "tour_name": "European Adventure",
                        "departure_date": "2024-06-15",
                        "return_date": "2024-06-25",
                        "destination": "Paris, France",
                        "group_size": 25
                    }
                ],
                "past_trips": [],
                "forms": [],
                "forms_pending_count": 2
            }
        }


# ============================================================================
# Authentication Models
# ============================================================================

class LoginRequest(BaseModel):
    """Login request payload for form submission"""
    username: str = Field(..., min_length=1, max_length=100, description="Portal username or email")
    password: str = Field(..., min_length=1, max_length=100, description="Portal password")
    company_code: str = Field(..., min_length=1, max_length=50, description="Company identifier")
    mode: str = Field(..., pattern="^(Test|Production)$", description="Environment mode")


class LoginAPIRequest(BaseModel):
    """Login request payload for API"""
    portal_user_name: str = Field(..., alias="portalUserName")
    portal_password: str = Field(..., alias="portalPassword")

    class Config:
        populate_by_name = True


class LoginAPIResponse(BaseModel):
    """Response from GP_PortalLogin API endpoint"""
    login_failed: bool = Field(..., alias="LoginFailed")
    type: Optional[int] = Field(None, alias="Type", description="1=Guide, 2=Vendor")
    guide_client_id: Optional[int] = Field(None, alias="GuideClientID")
    guide_first_name: Optional[str] = Field(None, alias="GuideFirstName")
    guide_last_name: Optional[str] = Field(None, alias="GuideLastName")
    guide_email: Optional[str] = Field(None, alias="GuideEmail")
    guide_vendor_id: Optional[int] = Field(None, alias="GuideVendorID")

    class Config:
        populate_by_name = True


class ForgotPasswordRequest(BaseModel):
    """Forgot password request payload"""
    username: str = Field(..., min_length=1, description="Username for password recovery")


class ForgotUsernameRequest(BaseModel):
    """Forgot username request payload"""
    email: str = Field(..., description="Email address for username recovery")


# ============================================================================
# API Response Models
# ============================================================================

class APIResponse(BaseModel):
    """Standard API response wrapper"""
    request_status: str = Field(..., description="Status: OK or ERROR")
    message: Optional[str] = Field(None, description="Error message if status is ERROR")
    data: Optional[dict] = Field(None, description="Response data if successful")


class GuideHomepageAPIResponse(BaseModel):
    """Response from getGuideHomepage API endpoint"""
    name: str
    guide_image: Optional[str] = Field(None, alias="GuideImage")
    future_trips: List[dict] = Field(default_factory=list, alias="FutureTrips")
    past_trips: List[dict] = Field(default_factory=list, alias="PastTrips")

    class Config:
        populate_by_name = True


class GuideFormsAPIResponse(BaseModel):
    """Response from getGuideForms API endpoint"""
    request_status: str = Field(..., alias="requestStatus")
    forms: List[dict] = Field(default_factory=list)

    class Config:
        populate_by_name = True


# ============================================================================
# Trip Departure Models (PAGE_TripDeparture from legacy system)
# ============================================================================

class TripGuide(BaseModel):
    """Guide/Trip Leader information"""
    guide_id: Optional[int] = Field(None, description="Guide's client ID")
    first_name: str = Field(..., description="Guide's first name")
    last_name: str = Field(..., description="Guide's last name")
    email: Optional[str] = Field(None, description="Guide's email")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class TripPassenger(BaseModel):
    """Passenger/Client information for a trip"""
    client_id: int = Field(..., description="Client unique ID")
    client_name: str = Field(..., description="Client full name")
    age: Optional[int] = Field(None, description="Client's age")
    gender: Optional[str] = Field(None, description="Client's gender")
    hometown: Optional[str] = Field(None, description="Client's hometown")
    nbr_past_trips: Optional[int] = Field(None, description="Number of past trips with company")
    notes: Optional[str] = Field(None, description="Special notes about the client")

    @field_validator('age', 'nbr_past_trips', mode='before')
    @classmethod
    def empty_string_to_none(cls, v):
        """Convert empty strings to None for optional int fields"""
        if v == '' or v is None:
            return None
        return v


class TripDocument(BaseModel):
    """Document associated with a trip or departure"""
    description: str = Field(..., description="Document description/name")
    document_url: str = Field(..., description="URL to access the document")
    document_type: Optional[str] = Field(None, description="Type: trip or departure")


class DepartureForm(BaseModel):
    """Form that needs to be completed for a departure"""
    form_id: Optional[str] = Field(None, description="Unique form ID")
    form_name: str = Field(..., description="Form display name")
    due_date: Optional[date] = Field(None, description="Form due date")
    departure_date: Optional[date] = Field(None, description="Trip departure date")
    url: Optional[str] = Field(None, description="URL to form")
    received: bool = Field(False, description="Whether form has been submitted")
    editable_after_submit: bool = Field(False, description="Can edit after submission")
    contact_email: Optional[str] = Field(None, description="Contact email for questions")
    contact_name: Optional[str] = Field(None, description="Contact name")
    status: Optional[FormStatus] = Field(None, description="Calculated form status")


class TripDepartureData(BaseModel):
    """Complete data for the Trip Departure page"""
    # Trip identification
    trip_departure_id: int = Field(..., description="Unique departure ID")
    trip_id: Optional[int] = Field(None, description="Trip ID")
    departure_id: Optional[str] = Field(None, description="Departure ID string")

    # Trip information
    trip_name: str = Field(..., description="Name of the trip")
    trip_dates: str = Field(..., description="Date range string (e.g., 'January 1-16, 2026')")
    thumbnail_image: Optional[str] = Field(None, description="Trip thumbnail/banner image URL")

    # Contacts
    guides: List[TripGuide] = Field(default_factory=list, description="Trip leaders/guides")
    trip_developer_name: Optional[str] = Field(None, description="Trip developer/Area Manager name")
    trip_developer_email: Optional[str] = Field(None, description="Trip developer email")

    # Passengers
    passengers: List[TripPassenger] = Field(default_factory=list, description="Trip passengers/clients")

    # Documents
    trip_documents: List[TripDocument] = Field(default_factory=list, description="General trip documents")
    departure_documents: List[TripDocument] = Field(default_factory=list, description="Departure-specific documents")

    # Forms
    forms: List[DepartureForm] = Field(default_factory=list, description="Forms to complete")
    forms_to_complete_count: int = Field(0, description="Number of incomplete forms")

    class Config:
        json_schema_extra = {
            "example": {
                "trip_departure_id": 47515,
                "trip_id": 1234,
                "departure_id": "WT2024-001",
                "trip_name": "European Adventure",
                "trip_dates": "June 15-25, 2024",
                "thumbnail_image": "https://example.com/images/trip.jpg",
                "guides": [
                    {"first_name": "John", "last_name": "Smith", "email": "john@example.com"}
                ],
                "trip_developer_name": "Jane Developer",
                "trip_developer_email": "jane@example.com",
                "passengers": [],
                "trip_documents": [],
                "departure_documents": [],
                "forms": [],
                "forms_to_complete_count": 0
            }
        }


class TripDepartureAPIResponse(BaseModel):
    """Response from GP_DeparturePage API endpoint"""
    trip_departure_id: int = Field(..., alias="TripDepartureID")
    trip_id: Optional[int] = Field(None, alias="TripID")
    departure_id: Optional[str] = Field(None, alias="DepartureID")
    trip_name: str = Field("", alias="tripName")
    trip_dates: str = Field("", alias="tripDates")
    thumbnail_image: Optional[str] = Field(None, alias="thumbNailImage")
    trip_developer_name: Optional[str] = Field(None, alias="tripDeveloperName")
    trip_developer_email: Optional[str] = Field(None, alias="tripDeveloperEmail")
    guides: List[dict] = Field(default_factory=list)
    passengers: List[dict] = Field(default_factory=list)
    trip_docs: List[dict] = Field(default_factory=list, alias="tripDocs")

    class Config:
        populate_by_name = True


# ============================================================================
# Client Page Models (PAGE_ClientV2 from legacy system)
# ============================================================================

class ClientData(BaseModel):
    """Complete data for the Client page (PAGE_ClientV2)"""
    client_id: int = Field(..., description="Client unique ID")
    first_name: str = Field(..., description="Client's first name")
    last_name: str = Field(..., description="Client's last name")
    email: Optional[str] = Field(None, description="Client's email")
    hometown: Optional[str] = Field(None, description="Client's hometown")
    gender: Optional[str] = Field(None, description="Client's gender (M/F)")
    age: Optional[int] = Field(None, description="Client's age")
    mobile: Optional[str] = Field(None, description="Client's cell phone number")
    number_of_trips: Optional[int] = Field(None, description="Number of past trips")

    # Medical and fitness information
    medical: Optional[str] = Field(None, description="Medical allergies (comma-separated)")
    fitness: Optional[str] = Field(None, description="Fitness level information (comma-separated)")
    dietary_restrictions: Optional[str] = Field(None, description="Dietary restrictions (comma-separated)")
    dietary_preferences: Optional[str] = Field(None, description="Dietary preferences (comma-separated)")

    # Trip history
    past_trips: Optional[str] = Field(None, description="Past trips (comma-separated)")
    past_trips_with_leader: Optional[str] = Field(None, description="Past trips with current trip leader (comma-separated)")
    future_trips: Optional[str] = Field(None, description="Future trips (comma-separated)")

    # Notes
    notes: Optional[str] = Field(None, description="Notes on client")

    @field_validator('age', 'number_of_trips', mode='before')
    @classmethod
    def empty_string_to_none(cls, v):
        """Convert empty strings to None for optional int fields"""
        if v == '' or v is None:
            return None
        return int(v) if isinstance(v, (str, float)) else v

    class Config:
        json_schema_extra = {
            "example": {
                "client_id": 15932,
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "hometown": "New York, NY",
                "gender": "M",
                "age": 45,
                "mobile": "+1-555-1234",
                "number_of_trips": 5,
                "medical": "Penicillin, Shellfish",
                "fitness": "Good, Regular exercise",
                "dietary_restrictions": "Gluten-free, Lactose intolerant",
                "dietary_preferences": "Vegetarian",
                "past_trips": "European Adventure, African Safari",
                "past_trips_with_leader": "European Adventure",
                "future_trips": "Alaska Expedition",
                "notes": "Prefers aisle seats"
            }
        }


class ClientAPIResponse(BaseModel):
    """Response from GP_GetClient API endpoint"""
    client_id: int = Field(..., alias="ClientID")
    first_name: str = Field("", alias="firstName")
    last_name: str = Field("", alias="lastName")
    email: Optional[str] = Field(None)
    hometown: Optional[str] = Field(None, alias="homeTown")
    gender: Optional[str] = Field(None)
    age: Optional[int] = Field(None)
    mobile: Optional[str] = Field(None)
    number_of_trips: Optional[int] = Field(None, alias="NumberOfTrips")
    medical: Optional[str] = Field(None)
    fitness: Optional[str] = Field(None)
    dietary_restrictions: Optional[str] = Field(None, alias="dietaryRestrictions")
    dietary_preferences: Optional[str] = Field(None, alias="dietaryPreferences")
    past_trips: Optional[str] = Field(None, alias="pastTrips")
    past_trips_with_leader: Optional[str] = Field(None, alias="pastTripsWithLeader")
    future_trips: Optional[str] = Field(None, alias="futureTrips")
    notes: Optional[str] = Field(None)
    birth_date: Optional[str] = Field(None, alias="birthDate")

    class Config:
        populate_by_name = True


# ============================================================================
# Trip Page Models (PAGE_Trip from legacy system)
# ============================================================================

class TripPageDocument(BaseModel):
    """Document associated with a trip"""
    description: str = Field(..., description="Document description/name")
    document_url: str = Field(..., description="URL to access the document")
    trip_year: Optional[str] = Field(None, description="Year of the itinerary")


class TripDepartureSummary(BaseModel):
    """Summary of a departure for the Trip page"""
    trip_departure_id: int = Field(..., description="Unique trip departure ID")
    dates: str = Field(..., description="Date range string")
    departure_date: Optional[date] = Field(None, description="Departure date for sorting")
    status: Optional[str] = Field(None, description="Departure status")
    guides: str = Field("", description="Comma-separated guide names")
    guide_ids: str = Field("", description="Comma-separated guide IDs")
    sign_ups: Optional[int] = Field(None, description="Number of clients signed up")
    comment: Optional[str] = Field(None, description="Departure comment")
    is_guide_on_trip: bool = Field(False, description="Whether current guide is on this departure")

    @field_validator('departure_date', mode='before')
    @classmethod
    def parse_departure_date(cls, v):
        """Parse departure date from various formats"""
        if v is None or v == '':
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            # Try common date formats
            for fmt in ['%Y-%m-%d', '%Y%m%d', '%m/%d/%Y']:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
        return None


class TripPageData(BaseModel):
    """Complete data for the Trip page"""
    trip_id: int = Field(..., description="Trip unique ID")
    trip_name: str = Field(..., description="Name of the trip")
    thumbnail_image: Optional[str] = Field(None, description="Trip thumbnail/banner image URL")

    # Documents
    documents: List[TripPageDocument] = Field(default_factory=list, description="Trip documents")

    # Departures
    future_departures: List[TripDepartureSummary] = Field(default_factory=list, description="Future departures")
    past_departures: List[TripDepartureSummary] = Field(default_factory=list, description="Past departures")


# ============================================================================
# Vendor Homepage Models (PAGE_VendorHomepage from legacy system)
# ============================================================================

class VendorTripSummary(BaseModel):
    """Model for a trip summary in the Vendor Future/Past trips tables"""
    trip_departure_id: Optional[int] = Field(None, alias="Trip_DepartureID", description="Unique trip departure ID")
    trip_id: Optional[int] = Field(None, alias="TripID", description="Trip ID for linking to trip page")
    trip_name: str = Field(..., alias="Trip_Name", description="Name of the trip")
    dates: str = Field(..., description="Date range string (e.g., 'January 1-16, 2026')")
    trip_leaders: Optional[str] = Field(None, alias="Trip_Leaders", description="Trip leaders/guides names")
    sign_ups: Optional[int] = Field(None, alias="SignUps", description="Number of travelers signed up")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "trip_departure_id": 12345,
                "trip_id": 5678,
                "trip_name": "European Adventure",
                "dates": "June 15-25, 2024",
                "trip_leaders": "John Smith, Jane Doe",
                "sign_ups": 25
            }
        }


class VendorForm(BaseModel):
    """Model for a vendor form in the Forms Due section"""
    form_id: Optional[str] = Field(None, description="Unique form ID (can be hash)")
    form_name: str = Field(..., alias="formName", description="Name of the form")
    trip_info: Optional[str] = Field(None, alias="TripInfo", description="Trip information")
    due_date: Optional[date] = Field(None, alias="dueDate", description="Form due date")
    departure_date: Optional[date] = Field(None, alias="DepartureDate", description="Trip departure date")
    received: bool = Field(False, description="Whether form has been submitted")
    editable_after_submit: bool = Field(False, alias="EditableAfterSubmit", description="Can be edited after submission")
    url: Optional[str] = Field(None, alias="URL", description="URL to access the form")

    # Contact information (varies by company)
    ops_name: Optional[str] = Field(None, alias="OpsName", description="Operations contact name")
    ops_email: Optional[str] = Field(None, alias="OpsEmail", description="Operations contact email")
    ops_phone: Optional[str] = Field(None, alias="OpsPhone", description="Operations contact phone")
    dev_name: Optional[str] = Field(None, alias="DevName", description="Developer contact name")
    dev_email: Optional[str] = Field(None, alias="DevEmail", description="Developer contact email")

    # Calculated fields (populated by service layer)
    status: Optional[FormStatus] = Field(None, description="Calculated form status")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "form_id": "ABC123",
                "form_name": "Vendor Service Agreement",
                "trip_info": "European Adventure - June 15, 2024",
                "due_date": "2024-05-30",
                "departure_date": "2024-06-15",
                "received": False,
                "editable_after_submit": True,
                "url": "https://example.com/forms/789",
                "ops_name": "Jane Operations",
                "ops_email": "ops@example.com"
            }
        }


class VendorHomepageData(BaseModel):
    """Complete data for the vendor homepage"""
    vendor_id: int = Field(..., description="Vendor's unique ID")
    vendor_name: str = Field(..., description="Vendor's name/company name")
    future_trips: List[VendorTripSummary] = Field(default_factory=list, description="List of upcoming trips")
    past_trips: List[VendorTripSummary] = Field(default_factory=list, description="List of completed trips")
    forms: List[VendorForm] = Field(default_factory=list, description="List of forms requiring attention")
    forms_pending_count: int = Field(0, description="Number of incomplete forms")

    class Config:
        json_schema_extra = {
            "example": {
                "vendor_id": 456,
                "vendor_name": "Alpine Adventures Inc.",
                "future_trips": [
                    {
                        "trip_departure_id": 12345,
                        "trip_id": 5678,
                        "trip_name": "European Adventure",
                        "dates": "June 15-25, 2024",
                        "trip_leaders": "John Smith",
                        "sign_ups": 25
                    }
                ],
                "past_trips": [],
                "forms": [],
                "forms_pending_count": 2
            }
        }


class VendorHomepageAPIResponse(BaseModel):
    """Response from getVendorHomepage API endpoint"""
    name: str
    future_trips: List[dict] = Field(default_factory=list, alias="FutureTrips")
    past_trips: List[dict] = Field(default_factory=list, alias="PastTrips")

    class Config:
        populate_by_name = True
