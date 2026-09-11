"""Business logic for guide-related operations"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from app.services.api_client import api_client
from app.utils.sentry_utils import capture_exception_with_context
from app.utils.trip_dates import parse_trip_start_date
from app.models.schemas import (
    GuideHomepageData,
    TripSummary,
    GuideForm,
    FormStatus,
    FormContact,
    GuideHomepageAPIResponse,
    GuideFormsAPIResponse,
    TripDepartureData,
    TripDepartureAPIResponse,
    TripGuide,
    TripPassenger,
    TripDocument,
    DepartureForm,
    TripPageData,
    TripPageDocument,
    TripDepartureSummary,
    ClientData,
    ClientAPIResponse
)
from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# GP_GetGuideForms drops any form whose dueDate is more than 60 days old, so an empty
# forms payload only proves "this guide has no forms" for recent/future departures.
# Outside this window the portal shows no forms badge at all instead of asserting.
NO_FORMS_ASSERTION_WINDOW_DAYS = 30


class GuideService:
    """Service for guide-related business logic"""

    def __init__(self):
        self.api_client = api_client

    async def get_guide_id_by_hash(
        self,
        guide_hash: str,
        company_code: str,
        mode: str
    ) -> int:
        """
        Resolve a guideHash to a guide_id using the Tourcube clientHash endpoint.
        """
        company_config = settings.get_company_config(company_code, mode)
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        result = await self.api_client.get(
            f"/tourcube/v1/clientHash/{guide_hash}"
        )

        # API may return a bare integer or a dict with various key names
        if isinstance(result, (int, str)):
            guide_id = result
        elif isinstance(result, dict):
            guide_id = (
                result.get("guide_id")
                or result.get("GuideID")
                or result.get("guideID")
                or result.get("client_id")
                or result.get("ClientID")
                or result.get("clientID")
            )
        else:
            guide_id = None

        if guide_id is None:
            raise ValueError("guideHash could not be resolved to a guide ID")

        try:
            return int(guide_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("guideHash returned an invalid guide ID") from exc

    async def get_guide_homepage(
        self,
        guide_id: int,
        company_code: str,
        mode: str
    ) -> GuideHomepageData:
        """
        Fetch and process guide homepage data

        Args:
            guide_id: Guide's unique identifier
            company_code: Company code for business rule customization
            mode: "Test" or "Production"

        Returns:
            GuideHomepageData with all processed information

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Configure api_client with correct credentials for this request
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        # Fetch homepage data from API
        homepage_response = await self.api_client.get(
            f"/tourcube/guidePortal/getGuideHomepage/{guide_id}"
        )

        # Parse API response
        homepage_data = GuideHomepageAPIResponse(**homepage_response)

        # Process trips
        future_trips = [
            self._parse_trip_summary(trip) for trip in homepage_data.future_trips
        ]
        past_trips = [
            self._parse_trip_summary(trip) for trip in homepage_data.past_trips
        ]

        # Process forms with status calculation.
        # forms_available tells the badge logic whether an empty list is an assertion
        # ("this guide has no forms") or simply the result of a failed call.
        forms, forms_pending_count, forms_available = await self._fetch_guide_forms(
            guide_id=guide_id,
            company_code=company_code,
            mode=mode,
        )

        # Sort past trips in descending order by departure date (most recent first).
        # When departure_date is missing, fall back to date.min so those trips sort last.
        past_trips.sort(
            key=lambda trip: trip.departure_date if trip.departure_date else date.min,
            reverse=True,
        )

        # Recompute the forms badge from the forms the portal actually knows about.
        # The API's own `formsDue` counter is not usable here — see _apply_forms_badges.
        self._apply_forms_badges(future_trips + past_trips, forms, forms_available)

        # Build complete homepage data
        return GuideHomepageData(
            guide_id=guide_id,
            guide_name=homepage_data.name,
            guide_image=homepage_data.guide_image,
            future_trips=future_trips,
            past_trips=past_trips,
            forms=forms,
            forms_pending_count=forms_pending_count
        )

    async def _fetch_guide_forms(
        self,
        guide_id: int,
        company_code: str,
        mode: str,
    ) -> Tuple[List[GuideForm], int, bool]:
        """
        Fetch every guide form in one call (GP_GetGuideForms with tripDepartureID = 0).

        Returns (forms, pending_count, available) where `available` is False when the
        call failed — an empty list is then "unknown", not "this guide has no forms".
        """
        forms: List[GuideForm] = []
        forms_pending_count = 0

        try:
            forms_response = await self.api_client.get(
                f"/tourcube/guidePortal/getGuideForms/{guide_id}/0"
            )

            # Parse forms API response
            # The API returns: {'forms': '[{...}, {...}]', 'requestStatus': 'OK'}
            # where 'forms' is a JSON string that needs to be parsed.
            # When the guide has no forms at all it returns {'requestStatus': 'EMPTY'}.
            forms_list = forms_response.get("forms", []) if isinstance(forms_response, dict) else forms_response

            # If forms_list is a JSON string, parse it
            if isinstance(forms_list, str):
                forms_list = json.loads(forms_list)

            # Ensure we have a list
            if not isinstance(forms_list, list):
                forms_list = []

            for form_dict in forms_list:
                # Parse per form: one malformed row must not discard the forms that did
                # parse, because losing them would silently disable the badge for EVERY
                # trip of this guide and fall back to the counter this fix replaces.
                try:
                    form = self._parse_guide_form(form_dict, company_code)
                except Exception as e:
                    logger.warning(
                        "Skipping unparseable guide form for guide %s: %s", guide_id, e
                    )
                    capture_exception_with_context(e, mode=mode, company_code=company_code)
                    continue

                forms.append(form)

                # Count forms that need attention (pending or expired)
                if form.status and form.status.status in ("pending", "expired"):
                    forms_pending_count += 1
        except Exception as e:
            # Log the error but continue without forms
            logger.warning("Failed to fetch guide forms for guide %s: %s", guide_id, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            return [], 0, False

        return forms, forms_pending_count, True

    def _apply_forms_badges(
        self,
        trips: List[TripSummary],
        forms: List[GuideForm],
        forms_available: bool,
    ) -> None:
        """
        Recompute each trip card's forms badge from the guide's actual forms.

        Why not use the API's `formsDue`: GP_GuideHomePage only increments it when
        `Received=False AND Receipt_Required=True AND DueDate<=today` (or, for
        Evaluation forms, `Travel_End_Date<today AND Received=False`). A form that is
        outstanding but not yet past due therefore arrives as formsDue = 0, and the
        template used to render that as "Complete" — the same value it renders for a
        trip that never had a form at all.

        The forms payload carries the raw `DepartureDate` and a `TripInfo` of
        "<Trip_Name> - <Mmm. D, YYYY>", so forms are attributed to a trip card by
        (trip name, departure date) — an exact key on both sides, not a heuristic.

        Sets forms_badge to one of:
            "due"      - at least one form is outstanding and actionable now
            "pending"  - forms exist and are unreturned, but none is due yet
            "complete" - forms exist and all of them were received
            "empty"    - the trip has no forms on record (recent departures only)
            None       - unknown; the card renders no badge
        """
        today = date.today()
        forms_by_trip = self._index_forms_by_trip(forms)
        assertion_cutoff = today - timedelta(days=NO_FORMS_ASSERTION_WINDOW_DAYS)

        for trip in trips:
            if not forms_available or trip.departure_date is None:
                # Nothing reliable to say. Keep the API's own alert if it raised one,
                # but never claim "Complete" on a guess.
                trip.has_forms = None
                trip.forms_incomplete_count = None
                trip.forms_badge = "due" if (trip.forms_due_count or 0) > 0 else None
                continue

            # The API's own counter, before it is replaced below. The two feeds do NOT
            # share a filter: GP_GetGuideForms drops rows more than 60 days past due,
            # while the homepage counter queries the forms table with no date floor at
            # all. So for an old trip the counter can be the ONLY surviving evidence
            # that something is outstanding, and it never over-reports (it counts only
            # unreceived + receipt-required + already due).
            api_forms_due = trip.forms_due_count or 0

            matched = forms_by_trip.get(self._forms_key(trip.tour_name, trip.departure_date), [])
            if matched:
                trip.has_forms = True
                trip.forms_due_count = sum(1 for form in matched if self._is_form_due(form, today))
                trip.forms_incomplete_count = sum(1 for form in matched if not form.received)

                if trip.forms_due_count:
                    trip.forms_badge = "due"
                elif trip.forms_incomplete_count:
                    trip.forms_badge = "pending"
                else:
                    trip.forms_badge = "complete"
            elif api_forms_due > 0:
                # No rows came back for this trip, but the counter says forms are due.
                # Keep the alert rather than going silent on a real one.
                trip.has_forms = True
                trip.forms_due_count = api_forms_due
                trip.forms_incomplete_count = None
                trip.forms_badge = "due"
            else:
                trip.has_forms = False
                trip.forms_due_count = 0
                trip.forms_incomplete_count = 0
                if trip.departure_date >= assertion_cutoff:
                    # No forms on record, and recent enough that GP_GetGuideForms would
                    # still be reporting them if they existed.
                    trip.forms_badge = "empty"
                else:
                    trip.forms_badge = None

    @staticmethod
    def _forms_key(trip_name: Optional[str], departure_date: Optional[date]) -> Tuple[str, Optional[date]]:
        """Join key shared by trip cards and forms: normalized trip name + departure date."""
        return ((trip_name or "").strip().casefold(), departure_date)

    def _index_forms_by_trip(self, forms: List[GuideForm]) -> Dict[Tuple[str, Optional[date]], List[GuideForm]]:
        """
        Group forms by (trip name, departure date), both taken from the form payload.

        The forms payload carries no TripID, so two departures of the same trip leaving
        on the same day would share one bucket and therefore one badge. That is the
        finest key the API offers.
        """
        index: Dict[Tuple[str, Optional[date]], List[GuideForm]] = {}
        for form in forms:
            if form.departure_date is None or not form.trip_info:
                # Without a departure date the form cannot be attributed to a card.
                continue
            # TripInfo is "<Trip_Name> - <Mmm. D, YYYY>"; trip names may contain " - ",
            # so split from the right.
            trip_name = form.trip_info.rsplit(" - ", 1)[0]
            index.setdefault(self._forms_key(trip_name, form.departure_date), []).append(form)
        return index

    @staticmethod
    def _is_form_due(form: GuideForm, today: date) -> bool:
        """
        Whether a form is outstanding AND actionable today.

        Mirrors the legacy counter in GP_GuideHomePage:

        - Evaluation forms follow their own rule and become due once the trip has
          travelled. Receipt_Required is deliberately NOT consulted for them, exactly
          as in the legacy code. The payload carries no Travel_End_Date, so the
          departure date stands in for it — which errs EARLY on a multi-day trip: the
          form can read as due from the day the trip starts rather than the day it ends.
        - Every other form is due only if it is required and the due date has arrived.
          A form that is not required is never "due" — at most "pending".
        """
        if form.received:
            return False
        if (form.form_type or "").strip().casefold() == "evaluation":
            return form.departure_date is not None and form.departure_date < today
        if not form.required:
            return False
        return form.due_date is None or form.due_date <= today

    def _parse_trip_summary(self, trip_dict: dict) -> TripSummary:
        """
        Parse raw trip dictionary into TripSummary model

        Args:
            trip_dict: Raw trip data from API

        Returns:
            TripSummary model instance
        """
        # Extract dates string (e.g., "January 1-16, 2026")
        dates = trip_dict.get("dates", "")

        # Parse departure date from Departure_Date field if available (format: YYYYMMDD).
        # GP_GuideHomePage only emits Departure_Date for PAST trips; future trips have
        # no machine-readable date at all, so fall back to parsing the `dates` range
        # string (exact inverse of the legacy GP_DateString) — this is also the join
        # key used to attribute forms to a trip card by (trip name, departure date).
        departure_date = None
        if trip_dict.get("Departure_Date"):
            departure_date = self._parse_date(trip_dict.get("Departure_Date"))
        if departure_date is None:
            departure_date = parse_trip_start_date(dates)

        return TripSummary(
            trip_departure_id=trip_dict.get("Trip_DepartureID"),
            trip_id=trip_dict.get("TripID"),
            tour_name=trip_dict.get("Trip_Name", ""),
            dates=dates,
            departure_date=departure_date,
            return_date=None,  # Not provided separately by API
            group_size=trip_dict.get("SignUps"),
            trip_leaders=trip_dict.get("Trip_Leaders"),  # Trip leaders/guides
            trip_contact_name=trip_dict.get("Trip_ContactName"),  # Replaces legacy devName
            trip_contact_label=trip_dict.get("Trip_ContactLabel"),  # Role label, e.g. "Trip Contact"
            ops_name=trip_dict.get("opsName"),  # Operations contact
            thumbnail_image=trip_dict.get("thumbnail"),
            forms_due_count=trip_dict.get("formsDue")
        )

    def _parse_guide_form(self, form_dict: dict, company_code: str) -> GuideForm:
        """
        Parse raw form dictionary into GuideForm model with status

        Args:
            form_dict: Raw form data from API
            company_code: Company code for business rules

        Returns:
            GuideForm model instance with calculated status
        """
        # Extract basic form data (note: API returns with capital first letters)
        form_id = form_dict.get("formID")  # Can be None for some forms
        form_name = form_dict.get("formName", "")
        description = form_dict.get("Description", "")
        trip_info = form_dict.get("TripInfo", "")
        due_date_str = form_dict.get("dueDate")
        departure_date_str = form_dict.get("DepartureDate")
        received = form_dict.get("received", False)
        required = form_dict.get("required", False)
        editable_after_submit = form_dict.get("EditableAfterSubmit", False)
        url = form_dict.get("URL", "")
        pdf_url = form_dict.get("pdfURL")
        form_type = form_dict.get("Type")

        # Contact information
        ops_name = form_dict.get("OpsName")
        ops_email = form_dict.get("OpsEmail")
        ops_phone = form_dict.get("OpsPhone")
        dev_name = form_dict.get("DevName")
        dev_email = form_dict.get("DevEmail")
        dev_phone = form_dict.get("DevPhone")

        # Parse dates
        due_date = self._parse_date(due_date_str) if due_date_str else None
        departure_date = self._parse_date(departure_date_str) if departure_date_str else None

        # Determine contact visibility based on company code
        # Legacy rule: CJ, JOB, IOT, WTAH should have contact hidden
        hidden_contact_companies = ["CJ", "JOB", "IOT", "WTAH"]
        show_contact = company_code not in hidden_contact_companies

        # Determine contact label based on company code
        if company_code == "WT":
            # Label: "Trip Developer: {DevName}"
            contact_label = f"Trip Developer: {dev_name}" if dev_name else None
        else:
            # Label: "Trip Contact: {OpsName} / {OpsPhone}"
            if ops_name:
                if ops_phone:
                    contact_label = f"Trip Contact: {ops_name} / {ops_phone}"
                else:
                    contact_label = f"Trip Contact: {ops_name}"
            else:
                contact_label = None

        # Determine contact based on company code and form data
        contact = self._get_form_contact(
            company_code=company_code,
            dev_name=dev_name,
            dev_email=dev_email,
            dev_phone=dev_phone,
            ops_name=ops_name,
            ops_email=ops_email,
            ops_phone=ops_phone
        )

        # Calculate form status
        status = self._calculate_form_status(
            received=received,
            editable_after_submit=editable_after_submit,
            due_date=due_date,
            url=url
        )

        return GuideForm(
            form_id=form_id,
            form_name=form_name,
            description=description,
            trip_info=trip_info,
            due_date=due_date,
            departure_date=departure_date,
            received=received,
            required=required,
            editable_after_submit=editable_after_submit,
            url=url,
            pdf_url=pdf_url,
            form_type=form_type,
            ops_name=ops_name,
            ops_email=ops_email,
            ops_phone=ops_phone,
            dev_name=dev_name,
            dev_email=dev_email,
            dev_phone=dev_phone,
            contact=contact,
            contact_label=contact_label,
            show_contact=show_contact,
            status=status
        )

    def _calculate_form_status(
        self,
        received: bool,
        editable_after_submit: bool,
        due_date: Optional[date],
        url: str
    ) -> FormStatus:
        """
        Calculate form status and button properties

        Business logic from legacy WebDev code:
        - If form received AND editable AND past cutoff date → disabled/grayed
        - If form received AND editable AND before cutoff date → clickable (blue)
        - If form received AND not editable → disabled/grayed (green)
        - If form not received → clickable pending (blue)
        - If form not received AND past due date → clickable expired (red)

        Args:
            received: Whether form has been submitted
            editable_after_submit: Can be edited after submission
            due_date: Form due date (cutoff is 30 days before)
            url: Form URL

        Returns:
            FormStatus with button properties
        """
        today = date.today()

        # Calculate edit cutoff date (30 days before due date)
        edit_cutoff_date = None
        if due_date:
            from datetime import timedelta
            edit_cutoff_date = due_date - timedelta(days=30)

        if received:
            if editable_after_submit:
                # Check if past edit cutoff date
                if edit_cutoff_date and today > edit_cutoff_date:
                    return FormStatus(
                        status="disabled",
                        button_text="View Form",
                        button_class="btn-secondary",
                        is_clickable=False,
                        url=None
                    )
                else:
                    return FormStatus(
                        status="completed",
                        button_text="Edit Form",
                        button_class="btn-success",
                        is_clickable=True,
                        url=url
                    )
            else:
                # Form received but not editable
                return FormStatus(
                    status="completed",
                    button_text="View Form",
                    button_class="btn-success",
                    is_clickable=False,
                    url=None
                )
        else:
            # Form not received
            if due_date and today > due_date:
                # Past due date
                return FormStatus(
                    status="expired",
                    button_text="Complete Form (Overdue)",
                    button_class="btn-danger",
                    is_clickable=True,
                    url=url
                )
            else:
                # Still pending
                return FormStatus(
                    status="pending",
                    button_text="Complete Form",
                    button_class="btn-danger",
                    is_clickable=True,
                    url=url
                )

    def _get_form_contact(
        self,
        company_code: str,
        dev_name: Optional[str] = None,
        dev_email: Optional[str] = None,
        dev_phone: Optional[str] = None,
        ops_name: Optional[str] = None,
        ops_email: Optional[str] = None,
        ops_phone: Optional[str] = None
    ) -> FormContact:
        """
        Get form contact information based on company code and API data

        Business rule from legacy:
        - WT company → Developer contact
        - All other companies → Operations contact

        Args:
            company_code: Company identifier
            dev_name: Developer name from API
            dev_email: Developer email from API
            dev_phone: Developer phone from API
            ops_name: Operations name from API
            ops_email: Operations email from API
            ops_phone: Operations phone from API

        Returns:
            FormContact with appropriate contact info from API data
        """
        if company_code == "WT":
            # Use Developer contact for WT companies
            return FormContact(
                name=dev_name or "Development Team",
                email=dev_email or "developer@tourcube.com",
                phone=dev_phone or ""
            )
        else:
            # Use Operations contact for other companies
            return FormContact(
                name=ops_name or "Operations Team",
                email=ops_email or "operations@tourcube.com",
                phone=ops_phone or ""
            )

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """
        Parse date string into date object

        Supports multiple formats:
        - YYYY-MM-DD
        - YYYYMMDD
        - MM/DD/YYYY

        Args:
            date_str: Date string to parse

        Returns:
            date object or None if parsing fails
        """
        if not date_str:
            return None

        # Try different date formats
        formats = [
            "%Y-%m-%d",      # ISO format
            "%Y%m%d",        # WebDev format
            "%m/%d/%Y",      # US format
            "%d/%m/%Y",      # International format
            "%b.-%d-%Y",     # API updateDate format (e.g. "Mar.-16-2026")
            "%b-%d-%Y"       # API updateDate fallback without dot
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        # If all formats fail, return None
        return None

    def _parse_trip_end_date(self, trip_dates: Optional[str]) -> Optional[date]:
        """
        Extract the trip end date from the tripDates string returned by the API.

        Supported formats:
        - Same month:   "March 10-21, 2026"               -> 2026-03-21
        - Cross month:  "March 28 - April 2, 2026"        -> 2026-04-02
        - Cross year:   "December 28, 2026 - January 5, 2027" -> 2027-01-05
        """
        import re

        if not trip_dates:
            return None
        s = trip_dates.strip()

        patterns = [
            # Cross-year: "Month D, YYYY - Month D, YYYY"
            r'^\w+\s+\d+,\s+\d+\s*-\s*(\w+)\s+(\d+),\s+(\d+)$',
            # Cross-month: "Month D - Month D, YYYY"
            r'^\w+\s+\d+\s*-\s*(\w+)\s+(\d+),\s+(\d+)$',
            # Same month: "Month D-D, YYYY" (first group captures start month used as end month)
            r'^(\w+)\s+\d+\s*-\s*(\d+),\s+(\d+)$',
        ]

        for pattern in patterns:
            m = re.match(pattern, s)
            if m:
                month, day, year = m.group(1), m.group(2), m.group(3)
                try:
                    return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date()
                except ValueError:
                    continue

        return None

    def _is_access_expired(self, trip_end_date: Optional[date], days: int = 45) -> bool:
        """
        Return True when the trip ended more than `days` days ago.

        When trip_end_date is unknown (unparseable), returns False so the
        guide keeps access — fail-open rather than locking users out.
        """
        if not trip_end_date:
            return False
        from datetime import timedelta
        return date.today() > trip_end_date + timedelta(days=days)

    async def get_trip_departure(
        self,
        trip_departure_id: int,
        user_id: int,
        user_role: str,
        company_code: str,
        mode: str
    ) -> TripDepartureData:
        """
        Fetch and process trip departure details

        Args:
            trip_departure_id: Unique trip departure identifier
            user_id: User's unique identifier (guide_id or vendor_id)
            user_role: User role ("Guide" or "Vendor")
            company_code: Company code for business rule customization
            mode: "Test" or "Production"

        Returns:
            TripDepartureData with all processed information

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Configure api_client with correct credentials for this request
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        # Fetch departure page data from API (GP_DeparturePage)
        departure_response = await self.api_client.get(
            f"/tourcube/guidePortal/getDeparturePage/{trip_departure_id}",
            params={"userId": user_id}
        )

        # Parse guides
        guides = []
        for guide_dict in departure_response.get("guides", []):
            guides.append(TripGuide(
                guide_id=guide_dict.get("guideID"),
                first_name=guide_dict.get("firstName", ""),
                last_name=guide_dict.get("lastName", ""),
                email=guide_dict.get("email")
            ))

        # Parse passengers
        passengers = []
        for passenger_dict in departure_response.get("passengers", []):
            passengers.append(TripPassenger(
                client_id=passenger_dict.get("clientID", 0),
                client_name=passenger_dict.get("clientName", ""),
                age=passenger_dict.get("age"),
                gender=passenger_dict.get("gender"),
                hometown=passenger_dict.get("hometown"),
                nbr_past_trips=passenger_dict.get("nbrPastTrips"),
                notes=passenger_dict.get("notes")
            ))

        # Parse departure documents
        departure_documents = []
        for doc_dict in departure_response.get("departureDocs", []):
            raw_date = doc_dict.get("updateDate") or doc_dict.get("dateUploaded") or doc_dict.get("uploadDate") or doc_dict.get("DateUploaded")
            parsed_date = self._parse_date(raw_date) if raw_date else None
            departure_documents.append(TripDocument(
                description=doc_dict.get("description", ""),
                document_url=doc_dict.get("documentURL", ""),
                document_type="departure",
                upload_date=parsed_date.strftime("%b %d, %Y") if parsed_date else None
            ))

        # Parse trip-level documents from getDeparturePage response
        trip_documents = []
        for doc_dict in departure_response.get("tripDocs", []):
            raw_date = doc_dict.get("updateDate") or doc_dict.get("dateUploaded") or doc_dict.get("uploadDate") or doc_dict.get("DateUploaded")
            parsed_date = self._parse_date(raw_date) if raw_date else None
            trip_documents.append(TripDocument(
                description=doc_dict.get("description", ""),
                document_url=doc_dict.get("documentURL", ""),
                document_type="trip",
                upload_date=parsed_date.strftime("%b %d, %Y") if parsed_date else None
            ))

        # Fetch forms data from API - use different endpoint based on user role
        # Wrap in try/except to handle API errors gracefully
        forms_response = {}
        try:
            if user_role == "Vendor":
                forms_response = await self.api_client.get(
                    f"/tourcube/guidePortal/getVendorForms/{user_id}/{trip_departure_id}"
                )
            else:
                forms_response = await self.api_client.get(
                    f"/tourcube/guidePortal/getGuideForms/{user_id}/{trip_departure_id}"
                )
        except Exception as e:
            # Log the error but continue with empty forms list
            logger.warning("Failed to fetch forms for %s %s: %s", user_role, user_id, e)
            # Report to Sentry for tracking with context
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            forms_response = {"forms": []}

        # Parse forms
        forms = []
        forms_to_complete_count = 0

        # The API may return forms as a JSON string
        forms_list = forms_response.get("forms", [])
        if isinstance(forms_list, str):
            import json
            forms_list = json.loads(forms_list)

        for form_dict in forms_list:
            due_date = self._parse_date(form_dict.get("dueDate"))
            departure_date = self._parse_date(form_dict.get("DepartureDate"))
            received = form_dict.get("received", False)
            editable_after_submit = form_dict.get("EditableAfterSubmit", False)
            url = form_dict.get("URL", "")

            # Determine contact visibility based on company code
            # Legacy rule: CJ, JOB, IOT, WTAH should have contact hidden
            hidden_contact_companies = ["CJ", "JOB", "IOT", "WTAH"]
            show_contact = company_code not in hidden_contact_companies

            # Determine contact and label based on company code
            ops_name = form_dict.get("OpsName")
            ops_phone = form_dict.get("OpsPhone")
            dev_name = form_dict.get("DevName")

            if company_code == "WT":
                contact_name = dev_name
                contact_email = form_dict.get("DevEmail")
                # Label: "Trip Developer: {DevName}"
                contact_label = f"Trip Developer: {dev_name}" if dev_name else None
            else:
                contact_name = ops_name
                contact_email = form_dict.get("OpsEmail")
                # Label: "Trip Contact: {OpsName} / {OpsPhone}"
                if ops_name:
                    if ops_phone:
                        contact_label = f"Trip Contact: {ops_name} / {ops_phone}"
                    else:
                        contact_label = f"Trip Contact: {ops_name}"
                else:
                    contact_label = None

            # Calculate form status
            status = self._calculate_form_status(
                received=received,
                editable_after_submit=editable_after_submit,
                due_date=due_date,
                url=url
            )

            form = DepartureForm(
                form_id=form_dict.get("formID"),
                form_name=form_dict.get("formName", ""),
                due_date=due_date,
                departure_date=departure_date,
                url=url,
                received=received,
                editable_after_submit=editable_after_submit,
                contact_email=contact_email,
                contact_name=contact_name,
                contact_label=contact_label,
                show_contact=show_contact,
                status=status
            )
            forms.append(form)

            # Count forms that need attention (pending or expired)
            if status and status.status in ("pending", "expired"):
                forms_to_complete_count += 1

        # Compute guide access expiration based on trip end date (45 days after trip ends)
        trip_dates_str = departure_response.get("tripDates", "")
        trip_end_date = self._parse_trip_end_date(trip_dates_str)
        access_expired = self._is_access_expired(trip_end_date)

        # Build complete trip departure data
        return TripDepartureData(
            trip_departure_id=trip_departure_id,
            trip_id=departure_response.get("TripID"),
            departure_id=departure_response.get("DepartureID"),
            trip_name=departure_response.get("tripName", ""),
            trip_dates=trip_dates_str,
            trip_end_date=trip_end_date,
            access_expired=access_expired,
            thumbnail_image=departure_response.get("thumbNailImage"),
            website_url=departure_response.get("websiteURL"),
            guides=guides,
            trip_contact_name=departure_response.get("tripContactName"),
            trip_contact_label=departure_response.get("tripContactLabel"),
            trip_contact_email=departure_response.get("tripContactEmail"),
            trip_contact_phone=departure_response.get("tripContactPhone"),
            passengers=passengers,
            trip_documents=trip_documents,
            departure_documents=departure_documents,
            forms=forms,
            forms_to_complete_count=forms_to_complete_count,
            departure_notes=departure_response.get("departureNotes") or None,
            documents_ready=bool(departure_response.get("documentsReady", False)),
        )

    async def get_trip_page(
        self,
        trip_id: int,
        guide_id: int,
        company_code: str,
        mode: str
    ) -> TripPageData:
        """
        Fetch and process trip page details

        Args:
            trip_id: Unique trip identifier
            guide_id: Guide's unique identifier (to check if guide is on departures)
            company_code: Company code for business rule customization
            mode: "Test" or "Production"

        Returns:
            TripPageData with all processed information

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Configure api_client with correct credentials for this request
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        # Fetch trip page data from API (GP_TripPage)
        trip_response = await self.api_client.get(
            f"/tourcube/guidePortal/getTripPage/{trip_id}",
            params={"userId": guide_id}
        )

        # Parse documents
        documents = []
        for doc_dict in trip_response.get("documents", []):
            documents.append(TripPageDocument(
                description=doc_dict.get("description", ""),
                document_url=doc_dict.get("documentURL", ""),
                trip_year=doc_dict.get("tripYear")
            ))

        # Parse departures - separate into future and past
        future_departures = []
        past_departures = []
        today = date.today()

        for dep_dict in trip_response.get("departures", []):
            # Skip canceled departures
            if dep_dict.get("status") == "Canceled":
                continue

            # Parse departure date
            dep_date_str = dep_dict.get("Dep_date", "")
            departure_date = None
            if dep_date_str:
                departure_date = self._parse_date(dep_date_str)

            # Format guide names (replace comma with comma-space)
            guides_str = dep_dict.get("guides", "")
            if guides_str:
                guides_str = guides_str.replace(",", ", ")

            # Check if current guide is on this departure
            guide_ids_str = dep_dict.get("guideIDs", "")
            is_guide_on_trip = False
            if guide_ids_str:
                guide_ids_list = [int(g.strip()) for g in guide_ids_str.split(",") if g.strip().isdigit()]
                is_guide_on_trip = guide_id in guide_ids_list

            departure = TripDepartureSummary(
                trip_departure_id=dep_dict.get("tripdepID", 0),
                dates=dep_dict.get("dates", ""),
                departure_date=departure_date,
                status=dep_dict.get("status"),
                guides=guides_str,
                guide_ids=guide_ids_str,
                sign_ups=dep_dict.get("SignUps"),
                comment=dep_dict.get("comment"),
                is_guide_on_trip=is_guide_on_trip
            )

            # Add to appropriate list based on date
            if departure_date and departure_date >= today:
                future_departures.append(departure)
            else:
                past_departures.append(departure)

        # Sort departures
        future_departures.sort(key=lambda x: x.departure_date or date.max)
        past_departures.sort(key=lambda x: x.departure_date or date.min, reverse=True)

        # Build complete trip page data
        return TripPageData(
            trip_id=trip_id,
            trip_name=trip_response.get("tripName", ""),
            thumbnail_image=trip_response.get("ThumbnailImageURL"),
            documents=documents,
            future_departures=future_departures,
            past_departures=past_departures
        )

    async def get_client_details(
        self,
        client_id: int,
        guide_id: int,
        company_code: str,
        mode: str
    ) -> ClientData:
        """
        Fetch and process client details (PAGE_ClientV2 from legacy)

        Args:
            client_id: Client's unique identifier
            company_code: Company code for business rule customization
            mode: "Test" or "Production"

        Returns:
            ClientData with all client information

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Configure api_client with correct credentials for this request
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        # Fetch client data from API (GP_GetClient)
        client_response = await self.api_client.get(
            f"/tourcube/guidePortal/getClientPage/{client_id}",
            params={"userId": guide_id}
        )

        # Calculate age from birthDate if age is 0 or None
        age = client_response.get("age")
        if not age or age == 0:
            birth_date_str = client_response.get("birthDate")
            if birth_date_str:
                birth_date = self._parse_date(birth_date_str)
                if birth_date:
                    today = date.today()
                    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

        # Parse trip lists — API returns list of dicts or None/string
        def _parse_trip_list(value):
            if not value or not isinstance(value, list):
                return []
            return value

        # Build ClientData from response
        return ClientData(
            client_id=client_id,
            first_name=client_response.get("firstName", ""),
            last_name=client_response.get("lastName", ""),
            email=client_response.get("email"),
            hometown=client_response.get("hometown"),
            gender=client_response.get("gender"),
            age=age,
            mobile=client_response.get("mobile"),
            number_of_trips=client_response.get("NumberOfTrips"),
            medical=client_response.get("medical"),
            fitness=client_response.get("fitness"),
            dietary_restrictions=client_response.get("dietaryRestrictions"),
            dietary_preferences=client_response.get("dietaryPreferences"),
            past_trips=_parse_trip_list(client_response.get("pastTrips")),
            past_trips_with_leader=_parse_trip_list(client_response.get("pastTripsWithLeader")),
            future_trips=_parse_trip_list(client_response.get("futureTrips")),
            notes=client_response.get("notes"),
            emergency_contact_name=client_response.get("emergencyContactName"),
            emergency_contact_relationship=client_response.get("emergencyContactRelationship"),
            emergency_contact_phone=client_response.get("emergencyContactPhone"),
            emergency_contact_email=client_response.get("emergencyContactEmail"),
        )


# Global guide service instance
guide_service = GuideService()
