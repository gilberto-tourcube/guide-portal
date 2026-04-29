"""Unit tests for app.services.vendor_service mappers."""

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
