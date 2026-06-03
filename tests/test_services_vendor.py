"""Unit tests for app.services.vendor_service mappers."""

from types import SimpleNamespace

import pytest

import app.services.vendor_service as vendor_module
from app.services.vendor_service import vendor_service


def test_parse_trip_summary_reads_trip_contact_fields():
    """_parse_trip_summary maps Trip_ContactName + Trip_ContactLabel from API payload."""
    api_trip = {
        "Trip_DepartureID": 9001,
        "TripID": 4242,
        "Trip_Name": "Climb Kilimanjaro: Northern Circuit Route",
        "dates": "March 1-15, 2026",
        "Departure_Date": "20260301",
        "SignUps": 12,
        "Trip_Leaders": "Samia Asindamu",
        "Trip_ContactName": "Jenny Gowan",
        "Trip_ContactLabel": "Trip Contact",
        "thumbnail": "https://example.com/kili.jpg",
        "formsDue": 2,
    }

    summary = vendor_service._parse_trip_summary(api_trip)

    assert summary.trip_contact_name == "Jenny Gowan"
    assert summary.trip_contact_label == "Trip Contact"
    assert summary.trip_leaders == "Samia Asindamu"
    assert summary.trip_name == "Climb Kilimanjaro: Northern Circuit Route"
    assert summary.tour_name == summary.trip_name
    assert summary.group_size == 12
    assert summary.sign_ups == 12


def test_parse_trip_summary_handles_missing_contact_fields():
    """When API omits Trip_ContactName/Label, mapper returns None for both."""
    api_trip = {
        "Trip_DepartureID": 1,
        "TripID": 1,
        "Trip_Name": "Sample",
        "dates": "Jan 1-7, 2026",
        "Trip_Leaders": "",
    }

    summary = vendor_service._parse_trip_summary(api_trip)

    assert summary.trip_contact_name is None
    assert summary.trip_contact_label is None
    assert summary.trip_leaders == ""


def test_parse_trip_summary_does_not_read_legacy_dev_name():
    """Mapper must ignore legacy `devName` field — it is no longer returned by the API."""
    api_trip = {
        "Trip_DepartureID": 1,
        "TripID": 1,
        "Trip_Name": "Sample",
        "dates": "Jan 1-7, 2026",
        "devName": "Should Not Be Read",
        "Trip_ContactName": "Real Contact",
        "Trip_ContactLabel": "Trip Contact",
    }

    summary = vendor_service._parse_trip_summary(api_trip)

    assert summary.trip_contact_name == "Real Contact"
    assert not hasattr(summary, "dev_name")


@pytest.mark.asyncio
async def test_vendor_homepage_orders_past_trips_most_recent_first(monkeypatch):
    """Vendor past trips should match Guide Portal ordering: newest completed trip first."""

    class FakeAPIClient:
        base_url = None
        api_key = None

        async def get(self, path):
            if path.endswith("/getVendorHomepage/123"):
                return {
                    "name": "Wildlife Vendor",
                    "FutureTrips": [],
                    "PastTrips": [
                        {
                            "Trip_DepartureID": 1,
                            "TripID": 101,
                            "Trip_Name": "Older Past Trip",
                            "dates": "May 10-20, 2023",
                        },
                        {
                            "Trip_DepartureID": 2,
                            "TripID": 102,
                            "Trip_Name": "Newest Past Trip",
                            "dates": "September 25-October 5, 2025",
                        },
                        {
                            "Trip_DepartureID": 3,
                            "TripID": 103,
                            "Trip_Name": "Missing Date Trip",
                            "dates": "Date TBD",
                        },
                    ],
                }
            if path.endswith("/getVendorForms/123/0"):
                return {"forms": []}
            raise AssertionError(f"Unexpected API path: {path}")

    monkeypatch.setattr(
        vendor_module,
        "settings",
        SimpleNamespace(
            get_company_config=lambda company_code, mode: SimpleNamespace(
                api_url="https://api.example.test",
                api_key="key",
            )
        ),
    )
    monkeypatch.setattr(vendor_service, "api_client", FakeAPIClient())

    homepage = await vendor_service.get_vendor_homepage(123, "WTGUIDE", "Test")

    assert [trip.trip_name for trip in homepage.past_trips] == [
        "Newest Past Trip",
        "Older Past Trip",
        "Missing Date Trip",
    ]
