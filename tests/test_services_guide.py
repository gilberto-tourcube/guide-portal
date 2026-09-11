"""Unit tests for app.services.guide_service mappers."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import app.services.guide_service as guide_module
from app.services.guide_service import guide_service
from app.utils.trip_dates import parse_trip_start_date


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


# ---------------------------------------------------------------------------
# Departure date parsing (exact inverse of the legacy GP_DateString)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dates,expected",
    [
        # same month
        ("September 7-21, 2026", date(2026, 9, 7)),
        # same year, different months
        ("November 22-December 6, 2026", date(2026, 11, 22)),
        # crossing the year boundary — the trailing year belongs to the END date
        ("December 28, 2026-January 5, 2027", date(2026, 12, 28)),
        # abbreviated month names
        ("Sep. 7-21, 2026", date(2026, 9, 7)),
        ("Not a date range", None),
        ("", None),
    ],
)
def test_parse_trip_start_date_covers_every_gp_datestring_shape(dates, expected):
    assert parse_trip_start_date(dates) == expected


def test_parse_trip_summary_uses_departure_date_over_the_dates_string():
    """Past trips carry Departure_Date — it must win over parsing the `dates` string."""
    api_trip = {
        "Trip_DepartureID": 1,
        "TripID": 1,
        "Trip_Name": "Sample",
        "dates": "January 1-7, 2020",  # deliberately a different date
        "Departure_Date": "20260728",
    }

    summary = guide_service._parse_trip_summary(api_trip)

    assert summary.departure_date == date(2026, 7, 28)


def test_parse_trip_summary_falls_back_to_dates_string_for_future_trips():
    """GP_GuideHomePage never emits Departure_Date for future trips."""
    api_trip = {
        "Trip_DepartureID": 1,
        "TripID": 1,
        "Trip_Name": "Sample",
        "dates": "September 7-21, 2026",
        # No Departure_Date key at all.
    }

    summary = guide_service._parse_trip_summary(api_trip)

    assert summary.departure_date == date(2026, 9, 7)


def test_range_string_round_trips_through_the_parser_on_every_date():
    """Guard: the test helper and the parser must agree for ANY run date.

    These tests build their fixtures from `date.today()`, so a helper that only
    works mid-month passes for 27 days and then breaks the build. Walk a full
    year, including every month boundary and the year boundary.
    """
    start = date(2026, 1, 1)
    for offset in range(400):
        day = start + timedelta(days=offset)
        for span in (1, 10):
            rendered = _range_string(day, days=span)
            assert parse_trip_start_date(rendered) == day, rendered


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_settings():
    return SimpleNamespace(
        get_company_config=lambda company_code, mode: SimpleNamespace(
            api_url="https://api.example.test",
            api_key="key",
        )
    )


def _install(monkeypatch, client):
    monkeypatch.setattr(guide_module, "settings", _fake_settings())
    # get_guide_homepage mutates the shared api_client singleton (no fan-out here,
    # so no request-scoped client is needed), so the fake simply replaces it.
    monkeypatch.setattr(guide_service, "api_client", client)


class FakeClient:
    """Fake APIClient driven by two canned payloads (homepage + forms)."""

    base_url = None
    api_key = None

    def __init__(self, homepage, forms=None):
        self.homepage = homepage
        self.forms = forms if forms is not None else {"requestStatus": "EMPTY"}

    async def get(self, path, params=None):
        if "/getGuideHomepage/" in path:
            return self.homepage
        if "/getGuideForms/" in path:
            if isinstance(self.forms, Exception):
                raise self.forms
            return self.forms
        raise AssertionError(f"Unexpected API path: {path}")


def _trip(departure_id, trip_id, name, dates):
    return {
        "Trip_DepartureID": departure_id,
        "TripID": trip_id,
        "Trip_Name": name,
        "dates": dates,
    }


def _days_ago(days):
    return date.today() - timedelta(days=days)


def _range_string(start, days=1):
    """Render a departure range exactly the way the legacy GP_DateString does.

    Faithful to UtilityProcedures.wdg:5536, all three shapes, because the tests
    below depend on the portal being able to read `start` back out of it. An
    earlier version dodged month boundaries by moving `start` to the 1st, which
    silently desynced the card's date from the form's DepartureDate whenever the
    run date landed near the end of a month.
    """
    end = start + timedelta(days=days)
    if start.year != end.year:
        return f"{start.strftime('%B')} {start.day}, {start.year}-{end.strftime('%B')} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start.strftime('%B')} {start.day}-{end.strftime('%B')} {end.day}, {start.year}"
    return f"{start.strftime('%B')} {start.day}-{end.day}, {start.year}"


def _form(trip_name, departure, *, received=False, required=True, form_type="Upload", due=None):
    return {
        "formName": "Cash Expense Report Upload",
        "TripInfo": f"{trip_name} - {departure.strftime('%b')}. {departure.day}, {departure.year}",
        "DepartureDate": departure.strftime("%Y%m%d"),
        "dueDate": (due or departure).strftime("%Y-%m-%d"),
        "received": received,
        "required": required,
        "Type": form_type,
    }


def _homepage_with_past_trip(name, start, forms_due=0):
    trip = _trip(58152, 58000, name, _range_string(start))
    trip["Departure_Date"] = start.strftime("%Y%m%d")
    trip["formsDue"] = forms_due
    return {"name": "Test Guide", "FutureTrips": [], "PastTrips": [trip]}


# ---------------------------------------------------------------------------
# The forms badge must stop lying
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forms_badge_is_pending_when_a_form_is_outstanding(monkeypatch):
    """formsDue = 0 while a form is unreturned must not render as Complete."""
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start, forms_due=0),
        forms={"requestStatus": "OK", "forms": [_form("Botswana Wildlife Safari", start, required=False)]},
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is True
    assert trip.forms_incomplete_count == 1
    assert trip.forms_badge == "pending"


@pytest.mark.asyncio
async def test_forms_badge_is_due_when_a_required_form_is_past_due(monkeypatch):
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start),
        forms={"requestStatus": "OK", "forms": [_form("Botswana Wildlife Safari", start, required=True)]},
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.forms_badge == "due"
    assert trip.forms_due_count == 1


@pytest.mark.asyncio
async def test_forms_badge_is_complete_only_when_every_form_was_received(monkeypatch):
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start),
        forms={"requestStatus": "OK", "forms": [_form("Botswana Wildlife Safari", start, received=True)]},
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.forms_badge == "complete"


@pytest.mark.asyncio
async def test_forms_badge_is_empty_when_a_recent_trip_never_had_a_form(monkeypatch):
    """No form on record must read as "No Forms", never as Complete."""
    start = _days_ago(26)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Okavango Delta", start),
        forms={"requestStatus": "EMPTY"},
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is False
    assert trip.forms_badge == "empty"


@pytest.mark.asyncio
async def test_forms_badge_is_silent_for_old_trips_without_forms(monkeypatch):
    """GP_GetGuideForms drops forms 60 days past due, so an old empty payload proves nothing."""
    start = _days_ago(400)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Okavango Delta", start),
        forms={"requestStatus": "EMPTY"},
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is False
    assert trip.forms_badge is None


@pytest.mark.asyncio
async def test_evaluation_form_is_only_due_after_the_trip_has_departed(monkeypatch):
    """Evaluations follow their own legacy rule: due once the trip travelled."""
    future_start = date.today() + timedelta(days=30)
    trip = _trip(56807, 58000, "Southern Tanzania", _range_string(future_start))
    trip["formsDue"] = 0
    client = FakeClient(
        homepage={"name": "Test Guide", "FutureTrips": [trip], "PastTrips": []},
        forms={
            "requestStatus": "OK",
            "forms": [_form("Southern Tanzania", future_start, form_type="Evaluation")],
        },
    )
    _install(monkeypatch, client)

    parsed = (await guide_service.get_guide_homepage(123, "WT", "Test")).future_trips[0]

    assert parsed.forms_due_count == 0
    assert parsed.forms_badge == "pending"


@pytest.mark.asyncio
async def test_evaluation_form_is_due_once_the_trip_has_departed(monkeypatch):
    """The other half of the Evaluation rule: after departure it becomes due.

    `required` is deliberately not consulted for Evaluations — the legacy
    counter does not consult it either.
    """
    start = _days_ago(20)
    trip = _trip(56807, 58000, "Southern Tanzania", _range_string(start))
    trip["Departure_Date"] = start.strftime("%Y%m%d")
    trip["formsDue"] = 0
    client = FakeClient(
        homepage={"name": "Test Guide", "FutureTrips": [], "PastTrips": [trip]},
        forms={
            "requestStatus": "OK",
            "forms": [
                _form("Southern Tanzania", start, form_type="Evaluation", required=False)
            ],
        },
    )
    _install(monkeypatch, client)

    parsed = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert parsed.forms_due_count == 1
    assert parsed.forms_badge == "due"


@pytest.mark.asyncio
async def test_forms_badge_never_claims_complete_when_the_forms_call_fails(monkeypatch):
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start, forms_due=0),
        forms=RuntimeError("forms endpoint down"),
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is None
    assert trip.forms_badge is None


@pytest.mark.asyncio
async def test_api_forms_due_alert_survives_a_failed_forms_call(monkeypatch):
    """Degraded path keeps the API's own alert; it only refuses to invent Complete."""
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start, forms_due=2),
        forms=RuntimeError("forms endpoint down"),
    )
    _install(monkeypatch, client)

    trip = (await guide_service.get_guide_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.forms_badge == "due"
    assert trip.forms_due_count == 2


@pytest.mark.asyncio
async def test_one_unparseable_form_does_not_discard_the_others(monkeypatch):
    """A single bad row must not disable the badge for the guide's whole list."""
    start = _days_ago(10)
    good = _form("Botswana Wildlife Safari", start, required=True)
    # Not a dict at all: _parse_guide_form's `.get()` calls raise AttributeError.
    bad = "not-a-form-row"
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start),
        forms={"requestStatus": "OK", "forms": [bad, good]},
    )
    _install(monkeypatch, client)

    homepage = await guide_service.get_guide_homepage(123, "WT", "Test")

    assert len(homepage.forms) == 1
    assert homepage.past_trips[0].forms_badge == "due"


@pytest.mark.asyncio
async def test_api_forms_due_survives_when_the_forms_list_aged_out(monkeypatch):
    """An old trip keeps its alert even though no form rows come back for it.

    GP_GetGuideForms drops rows more than 60 days past due; the homepage counter
    has no date floor. Trusting only the rows would silently drop a real alert on
    every trip older than that, which a live canary caught on a 2023 departure.
    """
    trip = _trip(9001, 700, "Ancient Trip", "September 5-13, 2023")
    trip["formsDue"] = 3
    client = FakeClient(
        homepage={"name": "Guide", "guideImage": None, "FutureTrips": [], "PastTrips": [trip]},
        forms={"requestStatus": "EMPTY"},
    )
    _install(monkeypatch, client)

    parsed = (await guide_service.get_guide_homepage(1, "WT", "Test")).past_trips[0]

    assert parsed.forms_badge == "due"
    assert parsed.forms_due_count == 3
    assert parsed.has_forms is True


@pytest.mark.asyncio
async def test_old_trip_without_forms_and_without_api_count_stays_silent(monkeypatch):
    """The counterpart: nothing on record and nothing claimed means no badge."""
    trip = _trip(9002, 700, "Ancient Trip", "September 5-13, 2023")
    trip["formsDue"] = 0
    client = FakeClient(
        homepage={"name": "Guide", "guideImage": None, "FutureTrips": [], "PastTrips": [trip]},
        forms={"requestStatus": "EMPTY"},
    )
    _install(monkeypatch, client)

    parsed = (await guide_service.get_guide_homepage(1, "WT", "Test")).past_trips[0]

    assert parsed.forms_badge is None
    assert parsed.has_forms is False
