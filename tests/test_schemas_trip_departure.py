"""Unit tests for TripDepartureAPIResponse and TripDepartureData schemas."""

from app.models.schemas import TripDepartureAPIResponse, TripDepartureData


def test_api_response_reads_new_trip_contact_aliases():
    """TripDepartureAPIResponse parses tripContactName/Label/Email/Phone from the live API payload."""
    payload = {
        "TripDepartureID": 58134,
        "TripID": 10397,
        "DepartureID": "EXPEDGRN072826",
        "tripName": "Western Greenland Expedition",
        "tripDates": "July 28-August 4, 2026",
        "thumbNailImage": "https://example.com/thumb.jpg",
        "tripContactName": "Emily Vernizzi",
        "tripContactLabel": "Trip Contact",
        "tripContactEmail": "emilyv@wildernesstravel.com",
        "tripContactPhone": "800-368-2794",
        "guides": [],
        "passengers": [],
    }

    parsed = TripDepartureAPIResponse(**payload)

    assert parsed.trip_contact_name == "Emily Vernizzi"
    assert parsed.trip_contact_label == "Trip Contact"
    assert parsed.trip_contact_email == "emilyv@wildernesstravel.com"
    assert parsed.trip_contact_phone == "800-368-2794"


def test_api_response_handles_missing_trip_contact_fields():
    """All four contact fields are optional and default to None."""
    payload = {
        "TripDepartureID": 1,
        "tripName": "Sample",
        "tripDates": "Jan 1-7, 2026",
        "guides": [],
        "passengers": [],
    }

    parsed = TripDepartureAPIResponse(**payload)

    assert parsed.trip_contact_name is None
    assert parsed.trip_contact_label is None
    assert parsed.trip_contact_email is None
    assert parsed.trip_contact_phone is None


def test_trip_departure_data_drops_legacy_developer_fields():
    """TripDepartureData no longer has the legacy trip_developer_* attributes."""
    data = TripDepartureData(
        trip_departure_id=1,
        trip_name="Sample",
        trip_dates="Jan 1-7, 2026",
        trip_contact_name="Emily Vernizzi",
        trip_contact_label="Trip Contact",
        trip_contact_email="emilyv@wildernesstravel.com",
        trip_contact_phone="800-368-2794",
    )

    assert data.trip_contact_name == "Emily Vernizzi"
    assert data.trip_contact_label == "Trip Contact"
    assert data.trip_contact_email == "emilyv@wildernesstravel.com"
    assert data.trip_contact_phone == "800-368-2794"
    assert not hasattr(data, "trip_developer_name")
    assert not hasattr(data, "trip_developer_email")
