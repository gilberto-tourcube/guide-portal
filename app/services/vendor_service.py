"""Business logic for vendor-related operations"""

from datetime import date, datetime
from typing import List, Optional
from app.services.api_client import api_client
from app.models.schemas import (
    VendorHomepageData,
    VendorTripSummary,
    VendorForm,
    FormStatus,
    VendorHomepageAPIResponse
)
from app.config import settings


class VendorService:
    """Service for vendor-related business logic"""

    def __init__(self):
        self.api_client = api_client

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

        # Configure api_client with correct credentials for this request
        self.api_client.base_url = company_config.api_url
        self.api_client.api_key = company_config.api_key

        # Fetch homepage data from API
        homepage_response = await self.api_client.get(
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

        # Sort past trips in descending order by departure date (most recent first)
        # Note: We don't have departure_date field in VendorTripSummary, so we'll keep original order
        # If needed, we can parse the dates string later

        # Process forms with status calculation
        forms = []
        forms_pending_count = 0

        # Try to fetch forms, but don't fail if API returns error
        try:
            forms_response = await self.api_client.get(
                f"/tourcube/guidePortal/getVendorForms/{vendor_id}/0"
            )

            # Parse forms API response
            # The API may return forms as a JSON string, so we need to parse it
            if isinstance(forms_response, str):
                import json
                forms_response = json.loads(forms_response)

            # If forms_response is a list, wrap it in a dict
            if isinstance(forms_response, list):
                forms_list = forms_response
            else:
                forms_list = forms_response if isinstance(forms_response, list) else []

            for form_dict in forms_list:
                form = self._parse_vendor_form(form_dict, company_code)
                forms.append(form)

                # Count pending forms
                if form.status and form.status.status == "pending":
                    forms_pending_count += 1
        except Exception as e:
            # Log the error but continue without forms
            print(f"Warning: Could not fetch vendor forms: {e}")
            # forms list remains empty

        # Build the complete response
        return VendorHomepageData(
            vendor_id=vendor_id,
            vendor_name=homepage_data.name,
            future_trips=future_trips,
            past_trips=past_trips,
            forms=forms,
            forms_pending_count=forms_pending_count
        )

    def _parse_trip_summary(self, trip_dict: dict) -> VendorTripSummary:
        """
        Parse a trip dictionary from API into VendorTripSummary model

        Args:
            trip_dict: Raw trip data from API

        Returns:
            VendorTripSummary model
        """
        return VendorTripSummary(**trip_dict)

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
                    button_class="btn-primary",
                    is_clickable=True,
                    url=form.url
                )


# Create a singleton instance
vendor_service = VendorService()
