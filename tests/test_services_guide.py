"""Unit tests for app.services.guide_service mappers."""

from app.services.guide_service import guide_service


def test_parse_trip_summary_reads_trip_contact_fields():
    """_parse_trip_summary maps Trip_ContactName + Trip_ContactLabel from API payload."""
    api_trip = {
        "Trip_DepartureID": 58134,
        "TripID": 10397,
        "Trip_Name": "Western Greenland Expedition",
        "dates": "July 28-August 4, 2026",
        "Departure_Date": "20260728",
        "SignUps": 7,
        "Trip_Leaders": "Rob Noonan2",
        "Trip_ContactName": "Emily Vernizzi",
        "Trip_ContactLabel": "Trip Contact",
        "thumbnail": "https://example.com/thumb.jpg",
        "formsDue": 0,
    }

    summary = guide_service._parse_trip_summary(api_trip)

    assert summary.trip_contact_name == "Emily Vernizzi"
    assert summary.trip_contact_label == "Trip Contact"
    assert summary.trip_leaders == "Rob Noonan2"
    assert summary.tour_name == "Western Greenland Expedition"
    assert summary.group_size == 7
    assert summary.trip_departure_id == 58134


def test_parse_trip_summary_handles_missing_contact_fields():
    """When API omits Trip_ContactName/Label, mapper returns None for both."""
    api_trip = {
        "Trip_DepartureID": 1,
        "TripID": 1,
        "Trip_Name": "Sample",
        "dates": "Jan 1-7, 2026",
        "Trip_Leaders": "Guide A",
    }

    summary = guide_service._parse_trip_summary(api_trip)

    assert summary.trip_contact_name is None
    assert summary.trip_contact_label is None
    assert summary.trip_leaders == "Guide A"


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

    summary = guide_service._parse_trip_summary(api_trip)

    assert summary.trip_contact_name == "Real Contact"
    # Legacy `dev_name` field has been removed from the schema entirely;
    # accessing it would raise AttributeError if the migration regressed.
    assert not hasattr(summary, "dev_name")
