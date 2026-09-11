"""Business logic for vendor-related operations"""

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from app.services.api_client import APIClient, api_client
from app.utils.sentry_utils import capture_exception_with_context
from app.models.schemas import (
    VendorHomepageData,
    VendorTripSummary,
    VendorForm,
    FormStatus,
    VendorHomepageAPIResponse
)
from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# GP_VendorForms drops any form whose dueDate is more than 60 days old, so an empty
# forms payload only proves "this trip has no forms" for recent/future departures.
# Outside this window the portal shows no forms badge at all instead of asserting.
NO_FORMS_ASSERTION_WINDOW_DAYS = 30


class VendorService:
    """Service for vendor-related business logic"""

    def __init__(self):
        self.api_client = api_client

    @staticmethod
    def _client_for(company_config) -> APIClient:
        """
        Build a REQUEST-SCOPED API client for this tenant.

        The module-level `api_client` is a process-wide singleton whose base_url and
        api_key are mutated in place. That is safe only while a request holds it across
        a single await; the vendor homepage now awaits several calls, including a
        fan-out, so a concurrent request for another tenant could overwrite the
        credentials mid-flight and send one company's key to another company's host.
        A per-request instance removes that window entirely.
        """
        client = APIClient()
        client.base_url = company_config.api_url
        client.api_key = company_config.api_key
        return client

    async def get_vendor_id_by_hash(
        self,
        vendor_hash: str,
        company_code: str,
        mode: str
    ) -> int:
        """
        Resolve a vendorHash to a vendor_id using the Tourcube getVendorByHash endpoint.

        The endpoint may return a bare integer, a dict with various key names,
        or the sentinel value ``0`` when the hash is unknown.
        """
        company_config = settings.get_company_config(company_code, mode)
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        result = await self.api_client.get(
            f"/tourcube/guidePortal/getVendorByHash/{vendor_hash}"
        )

        # API may return a bare integer or a dict with various key names
        if isinstance(result, (int, str)):
            vendor_id = result
        elif isinstance(result, dict):
            vendor_id = (
                result.get("vendor_id")
                or result.get("VendorID")
                or result.get("vendorID")
                or result.get("VendorId")
            )
        else:
            vendor_id = None

        try:
            vendor_id_int = int(vendor_id) if vendor_id is not None else None
        except (TypeError, ValueError) as exc:
            raise ValueError("vendorHash returned an invalid vendor ID") from exc

        # API returns 0 when the hash is unknown or stale
        if not vendor_id_int:
            raise ValueError("vendorHash could not be resolved to a vendor ID")

        return vendor_id_int

    async def get_vendor_homepage(
        self,
        vendor_id: int,
        company_code: str,
        mode: str
    ) -> VendorHomepageData:
        """
        Fetch and process vendor homepage data

        Args:
            vendor_id: Vendor's unique identifier
            company_code: Company code for business rule customization
            mode: "Test" or "Production"

        Returns:
            VendorHomepageData with all processed information

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Request-scoped client: this method awaits several calls, so it must not rely
        # on credentials parked on the shared singleton (see _client_for).
        client = self._client_for(company_config)

        # Fetch homepage data from API
        homepage_response = await client.get(
            f"/tourcube/guidePortal/getVendorHomepage/{vendor_id}"
        )

        # Parse API response
        homepage_data = VendorHomepageAPIResponse(**homepage_response)

        # Process trips
        future_trips = [
            self._parse_trip_summary(trip) for trip in homepage_data.future_trips
        ]
        past_trips = [
            self._parse_trip_summary(trip) for trip in homepage_data.past_trips
        ]

        # Process forms with status calculation.
        # forms_available tells the badge logic whether an empty list is an assertion
        # ("this vendor has no forms") or simply the result of a failed call.
        forms, forms_pending_count, forms_available = await self._fetch_vendor_forms(
            client=client,
            vendor_id=vendor_id,
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

        # Build the complete response
        return VendorHomepageData(
            vendor_id=vendor_id,
            vendor_name=homepage_data.name,
            future_trips=future_trips,
            past_trips=past_trips,
            forms=forms,
            forms_pending_count=forms_pending_count
        )

    async def _fetch_vendor_forms(
        self,
        client: APIClient,
        vendor_id: int,
        company_code: str,
        mode: str,
    ) -> Tuple[List[VendorForm], int, bool]:
        """
        Fetch every vendor form in one call (GP_VendorForms with tripDepartureID = 0).

        Returns (forms, pending_count, available) where `available` is False when the
        call failed — an empty list is then "unknown", not "this vendor has no forms".
        """
        forms: List[VendorForm] = []
        forms_pending_count = 0

        try:
            forms_response = await client.get(
                f"/tourcube/guidePortal/getVendorForms/{vendor_id}/0"
            )

            # Parse forms API response
            # The API returns: {'forms': '[{...}, {...}]', 'requestStatus': 'OK'}
            # where 'forms' is a JSON string that needs to be parsed.
            # When the vendor has no forms at all it returns {'requestStatus': 'EMPTY'}.
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
                # trip of this vendor and fall back to the counter this fix replaces.
                try:
                    form = self._parse_vendor_form(form_dict, company_code)
                except Exception as e:
                    logger.warning(
                        "Skipping unparseable vendor form for vendor %s: %s", vendor_id, e
                    )
                    capture_exception_with_context(e, mode=mode, company_code=company_code)
                    continue

                forms.append(form)

                # Count forms that need attention (pending or overdue)
                if form.status and form.status.status in ("pending", "overdue"):
                    forms_pending_count += 1
        except Exception as e:
            # Log the error but continue without forms
            logger.warning("Failed to fetch vendor forms for vendor %s: %s", vendor_id, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            return [], 0, False

        return forms, forms_pending_count, True

    def _apply_forms_badges(
        self,
        trips: List[VendorTripSummary],
        forms: List[VendorForm],
        forms_available: bool,
    ) -> None:
        """
        Recompute each trip card's forms badge from the vendor's actual forms.

        Why not use the API's `formsDue`: GP_VendorHomepage only increments it when
        `Received=False AND Receipt_Required=True AND DueDate<=today` (or, for
        Evaluation forms, `Travel_End_Date<today AND Received=False`). A form that is
        outstanding but not yet past due therefore arrives as formsDue = 0, and the
        template used to render that as "Complete" — the same value it renders for a
        trip that never had a form at all.

        The forms payload carries the raw `DepartureDate` (YYYYMMDD) and a `TripInfo`
        of "<Trip_Name> - <Mmm. D, YYYY>", so forms are attributed to a trip card by
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

            matched = forms_by_trip.get(self._forms_key(trip.trip_name, trip.departure_date), [])
            trip.has_forms = bool(matched)
            trip.forms_due_count = sum(1 for form in matched if self._is_form_due(form, today))
            trip.forms_incomplete_count = sum(1 for form in matched if not form.received)

            if trip.forms_due_count:
                trip.forms_badge = "due"
            elif trip.forms_incomplete_count:
                trip.forms_badge = "pending"
            elif matched:
                trip.forms_badge = "complete"
            elif trip.departure_date >= assertion_cutoff:
                # No forms on record, and recent enough that GP_VendorForms would still
                # be reporting them if they existed.
                trip.forms_badge = "empty"
            else:
                trip.forms_badge = None

    @staticmethod
    def _forms_key(trip_name: Optional[str], departure_date: Optional[date]) -> Tuple[str, Optional[date]]:
        """Join key shared by trip cards and forms: normalized trip name + departure date."""
        return ((trip_name or "").strip().casefold(), departure_date)

    def _index_forms_by_trip(self, forms: List[VendorForm]) -> Dict[Tuple[str, Optional[date]], List[VendorForm]]:
        """
        Group forms by (trip name, departure date), both taken from the form payload.

        The forms payload carries no TripID, so two departures of the same trip leaving
        on the same day would share one bucket and therefore one badge. That is the
        finest key the API offers.
        """
        index: Dict[Tuple[str, Optional[date]], List[VendorForm]] = {}
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
    def _is_form_due(form: VendorForm, today: date) -> bool:
        """
        Whether a form is outstanding AND actionable today.

        Mirrors the legacy counter in GP_VendorHomepage:

        - Evaluation forms follow their own rule and become due once the trip has
          travelled. Receipt_Required is deliberately NOT consulted for them, exactly
          as in the legacy code. The payload carries no Travel_End_Date, so the
          departure date stands in for it — which errs EARLY on a multi-day trip: the
          form can read as due from the day the trip starts rather than the day it ends.
        - Every other form is due only if a receipt is required and the due date has
          arrived. A form that requires no receipt is never "due" — at most "pending".
        """
        if form.received:
            return False
        if (form.form_type or "").strip().casefold() == "evaluation":
            return form.departure_date is not None and form.departure_date < today
        if not form.receipt_required:
            return False
        return form.due_date is None or form.due_date <= today

    def _parse_trip_summary(self, trip_dict: dict) -> VendorTripSummary:
        """
        Parse a trip dictionary from API into VendorTripSummary model.

        Populates the extended fields used by the shared trip-card template
        (mirroring guide_service._parse_trip_summary): thumbnail_image,
        forms_due_count, trip_contact_name, trip_contact_label, group_size,
        departure_date.
        """
        sign_ups = trip_dict.get("SignUps")
        trip_name = trip_dict.get("Trip_Name", "")

        departure_date = None
        if trip_dict.get("Departure_Date"):
            departure_date = self._parse_date(trip_dict.get("Departure_Date"))
        if departure_date is None:
            departure_date = self._parse_trip_start_date(trip_dict.get("dates"))

        return VendorTripSummary(
            trip_departure_id=trip_dict.get("Trip_DepartureID"),
            trip_id=trip_dict.get("TripID"),
            trip_name=trip_name,
            tour_name=trip_name,
            dates=trip_dict.get("dates", ""),
            trip_leaders=trip_dict.get("Trip_Leaders"),
            sign_ups=sign_ups,
            group_size=sign_ups,
            thumbnail_image=trip_dict.get("thumbnail"),
            trip_contact_name=trip_dict.get("Trip_ContactName"),  # Replaces legacy devName
            trip_contact_label=trip_dict.get("Trip_ContactLabel"),  # Role label, e.g. "Trip Contact"
            forms_due_count=trip_dict.get("formsDue"),
            departure_date=departure_date,
        )

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse common date string formats returned by the API."""
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    # Exact inverse of the legacy GP_DateString (UtilityProcedures.wdg), which renders
    # a departure as one of three shapes:
    #   same month  -> "September 7-21, 2026"
    #   same year   -> "November 22-December 6, 2026"
    #   cross year  -> "December 28, 2026-January 5, 2027"
    # The cross-year shape must be matched FIRST: a greedy "take the trailing year"
    # regex reads it as 2027 and puts the departure a year late.
    _CROSS_YEAR_RANGE = re.compile(
        r"^\s*([A-Za-z.]+)\s+(\d{1,2})\s*,\s*(\d{4})\s*-\s*[A-Za-z.]+\s+\d{1,2}\s*,\s*\d{4}\s*$"
    )
    _SAME_YEAR_RANGE = re.compile(
        r"^\s*([A-Za-z.]+)\s+(\d{1,2})\s*-\s*(?:[A-Za-z.]+\s+)?\d{1,2}\s*,\s*(\d{4})\s*$"
    )
    # Anything else that still looks like "<Month> <day> ... , <year>" (e.g. a single day).
    _LOOSE_RANGE = re.compile(r"^\s*([A-Za-z.]+)\s+(\d{1,2})\b.*,\s*(\d{4})\s*$")

    def _parse_trip_start_date(self, trip_dates: Optional[str]) -> Optional[date]:
        """Extract the starting date from vendor trip date ranges like `May 10-20, 2023`."""
        if not trip_dates:
            return None

        for pattern in (self._CROSS_YEAR_RANGE, self._SAME_YEAR_RANGE, self._LOOSE_RANGE):
            match = pattern.match(trip_dates)
            if not match:
                continue

            month, day, year = match.groups()
            normalized = f"{month.rstrip('.')} {day} {year}"

            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(normalized, fmt).date()
                except ValueError:
                    continue
        return None

    def _parse_vendor_form(self, form_dict: dict, company_code: str) -> VendorForm:
        """
        Parse a form dictionary from API into VendorForm model with calculated status

        Args:
            form_dict: Raw form data from API
            company_code: Company code for business rule customization

        Returns:
            VendorForm model with calculated status
        """
        # Create the form model from the dictionary
        form = VendorForm(**form_dict)

        # Determine contact visibility based on company code
        # Legacy rule: CJ, JOB, IOT, WTAH should have contact hidden
        hidden_contact_companies = ["CJ", "JOB", "IOT", "WTAH"]
        form.show_contact = company_code not in hidden_contact_companies

        # Determine contact and label based on company code
        if company_code == "WT":
            form.contact_name = form.dev_name
            form.contact_email = form.dev_email
            # Label: "Trip Developer: {DevName}"
            if form.dev_name:
                form.contact_label = f"Trip Developer: {form.dev_name}"
        else:
            form.contact_name = form.ops_name
            form.contact_email = form.ops_email
            # Label: "Trip Contact: {OpsName} / {OpsPhone}"
            if form.ops_name:
                if form.ops_phone:
                    form.contact_label = f"Trip Contact: {form.ops_name} / {form.ops_phone}"
                else:
                    form.contact_label = f"Trip Contact: {form.ops_name}"

        # Calculate form status
        form.status = self._calculate_form_status(form, company_code)

        return form

    def _calculate_form_status(self, form: VendorForm, company_code: str) -> FormStatus:
        """
        Calculate the status of a vendor form based on business rules

        Business Rules (from legacy GP_VendorForms procedure):
        1. If form is received (submitted):
           - If editable_after_submit = True:
             - If departure_date - 30 days <= today: status = "disabled" (too close to departure)
             - Else: status = "completed" (can still edit)
           - Else: status = "completed" (submitted, not editable)

        2. If form is NOT received:
           - If due_date <= today: status = "overdue"
           - Else: status = "pending"

        Args:
            form: VendorForm model
            company_code: Company code for any company-specific rules

        Returns:
            FormStatus with calculated state
        """
        today = date.today()

        # Check if form has been received (submitted)
        if form.received:
            # Form has been submitted
            if form.editable_after_submit:
                # Check if we're within 30 days of departure
                if form.departure_date:
                    # Calculate cutoff date (30 days before departure)
                    from datetime import timedelta
                    cutoff_date = form.departure_date - timedelta(days=30)

                    if cutoff_date <= today:
                        # Too close to departure, cannot edit anymore
                        return FormStatus(
                            status="disabled",
                            button_text="View Form",
                            button_class="btn-secondary",
                            is_clickable=False,
                            url=None
                        )
                    else:
                        # Can still edit
                        return FormStatus(
                            status="completed",
                            button_text="View/Edit Form",
                            button_class="btn-success",
                            is_clickable=True,
                            url=form.url
                        )
                else:
                    # No departure date, allow editing
                    return FormStatus(
                        status="completed",
                        button_text="View/Edit Form",
                        button_class="btn-success",
                        is_clickable=True,
                        url=form.url
                    )
            else:
                # Not editable after submit
                return FormStatus(
                    status="completed",
                    button_text="View Form",
                    button_class="btn-secondary",
                    is_clickable=False,
                    url=None
                )
        else:
            # Form has NOT been submitted
            if form.due_date and form.due_date <= today:
                # Past due date
                return FormStatus(
                    status="overdue",
                    button_text="Complete Form",
                    button_class="btn-danger",
                    is_clickable=True,
                    url=form.url
                )
            else:
                # Still pending
                return FormStatus(
                    status="pending",
                    button_text="Complete Form",
                    button_class="btn-danger",
                    is_clickable=True,
                    url=form.url
                )


# Create a singleton instance
vendor_service = VendorService()
