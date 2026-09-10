"""Unit tests for app.services.vendor_service mappers."""

from datetime import date, timedelta
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
            if "/getTripPage/" in path:
                # No departure rows -> status unknown -> every trip is kept.
                return {"requestStatus": "OK", "departures": []}
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
    monkeypatch.setattr(vendor_service, "_client_for", lambda company_config: FakeAPIClient())

    homepage = await vendor_service.get_vendor_homepage(123, "WTGUIDE", "Test")

    assert [trip.trip_name for trip in homepage.past_trips] == [
        "Newest Past Trip",
        "Older Past Trip",
        "Missing Date Trip",
    ]


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
    assert vendor_service._parse_trip_start_date(dates) == expected


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
    monkeypatch.setattr(vendor_module, "settings", _fake_settings())
    # The homepage builds a request-scoped client, so that factory is the seam.
    monkeypatch.setattr(vendor_service, "_client_for", lambda company_config: client)


class FakeClient:
    """Fake APIClient driven by three canned payloads."""

    base_url = None
    api_key = None

    def __init__(self, homepage, forms=None, trip_pages=None, trip_page_error=None):
        self.homepage = homepage
        self.forms = forms if forms is not None else {"requestStatus": "EMPTY"}
        self.trip_pages = trip_pages or {}
        self.trip_page_error = trip_page_error
        self.trip_page_calls = []

    async def get(self, path, params=None):
        if "/getVendorHomepage/" in path:
            return self.homepage
        if "/getVendorForms/" in path:
            if isinstance(self.forms, Exception):
                raise self.forms
            return self.forms
        if "/getTripPage/" in path:
            trip_id = int(path.rsplit("/", 1)[1])
            self.trip_page_calls.append(trip_id)
            if self.trip_page_error is not None:
                raise self.trip_page_error
            return {"requestStatus": "OK", "departures": self.trip_pages.get(trip_id, [])}
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


# ---------------------------------------------------------------------------
# Item 1 — canceled departures must not be listed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vendor_homepage_drops_canceled_departures(monkeypatch):
    """A departure that getTripPage reports as Canceled disappears from both lists."""
    client = FakeClient(
        homepage={
            "name": "African Environments",
            "FutureTrips": [
                _trip(61689, 10389, "Grand Danube", "September 7-21, 2026"),
                _trip(61690, 10389, "Grand Danube", "September 21-October 5, 2026"),
            ],
            "PastTrips": [
                _trip(61600, 10389, "Grand Danube", "March 1-15, 2026"),
            ],
        },
        trip_pages={
            10389: [
                {"tripdepID": 61689, "status": "Canceled"},
                {"tripdepID": 61690, "status": "Open"},
                {"tripdepID": 61600, "status": "Canceled"},
            ]
        },
    )
    _install(monkeypatch, client)

    homepage = await vendor_service.get_vendor_homepage(123, "WT", "Test")

    assert [t.trip_departure_id for t in homepage.future_trips] == [61690]
    assert homepage.past_trips == []
    # One call per DISTINCT TripID, not one per departure row.
    assert client.trip_page_calls == [10389]


@pytest.mark.asyncio
async def test_vendor_homepage_keeps_trips_when_status_lookup_fails(monkeypatch):
    """A network failure must never hide a legitimate trip."""
    client = FakeClient(
        homepage={
            "name": "African Environments",
            "FutureTrips": [_trip(61689, 10389, "Grand Danube", "September 7-21, 2026")],
            "PastTrips": [],
        },
        trip_page_error=RuntimeError("boom"),
    )
    _install(monkeypatch, client)

    homepage = await vendor_service.get_vendor_homepage(123, "WT", "Test")

    assert [t.trip_departure_id for t in homepage.future_trips] == [61689]
    assert homepage.future_trips[0].departure_status is None


@pytest.mark.asyncio
async def test_vendor_homepage_keeps_departures_outside_trip_page_window(monkeypatch):
    """getTripPage only covers +/-730 days; older departures are absent, not canceled."""
    client = FakeClient(
        homepage={
            "name": "African Environments",
            "FutureTrips": [],
            "PastTrips": [_trip(48038, 10389, "Grand Danube", "July 3-13, 2023")],
        },
        trip_pages={10389: [{"tripdepID": 61690, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    homepage = await vendor_service.get_vendor_homepage(123, "WT", "Test")

    assert [t.trip_departure_id for t in homepage.past_trips] == [48038]


# ---------------------------------------------------------------------------
# Items 2 and 3 — the forms badge must stop lying
# ---------------------------------------------------------------------------


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
    trip["formsDue"] = forms_due
    return {"name": "Capricorn Safaris", "FutureTrips": [], "PastTrips": [trip]}


@pytest.mark.asyncio
async def test_forms_badge_is_pending_when_a_form_is_outstanding(monkeypatch):
    """Defect 2: formsDue = 0 while a form is unreturned must not render as Complete."""
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start, forms_due=0),
        forms={"requestStatus": "OK", "forms": [_form("Botswana Wildlife Safari", start, required=False)]},
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is True
    assert trip.forms_incomplete_count == 1
    assert trip.forms_badge == "pending"


@pytest.mark.asyncio
async def test_forms_badge_is_due_when_a_required_form_is_past_due(monkeypatch):
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start),
        forms={"requestStatus": "OK", "forms": [_form("Botswana Wildlife Safari", start, required=True)]},
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.forms_badge == "due"
    assert trip.forms_due_count == 1


@pytest.mark.asyncio
async def test_forms_badge_is_complete_only_when_every_form_was_received(monkeypatch):
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start),
        forms={"requestStatus": "OK", "forms": [_form("Botswana Wildlife Safari", start, received=True)]},
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.forms_badge == "complete"


@pytest.mark.asyncio
async def test_forms_badge_is_empty_when_a_recent_trip_never_had_a_form(monkeypatch):
    """Defect 3: no form on record must read as "No Forms", never as Complete."""
    start = _days_ago(26)  # the reported Okavango case was 26 days old
    client = FakeClient(
        homepage=_homepage_with_past_trip("Okavango Delta", start),
        forms={"requestStatus": "EMPTY"},
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is False
    assert trip.forms_badge == "empty"


@pytest.mark.asyncio
async def test_forms_badge_is_silent_for_old_trips_without_forms(monkeypatch):
    """GP_VendorForms drops forms 60 days past due, so an old empty payload proves nothing."""
    start = _days_ago(400)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Okavango Delta", start),
        forms={"requestStatus": "EMPTY"},
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is False
    assert trip.forms_badge is None


@pytest.mark.asyncio
async def test_evaluation_form_is_only_due_after_the_trip_has_departed(monkeypatch):
    """Evaluations follow their own legacy rule: due once the trip travelled."""
    future_start = date.today() + timedelta(days=30)
    trip = _trip(56807, 58000, "Southern Tanzania", _range_string(future_start))
    trip["formsDue"] = 0
    client = FakeClient(
        homepage={"name": "Wildlife Explorer", "FutureTrips": [trip], "PastTrips": []},
        forms={
            "requestStatus": "OK",
            "forms": [_form("Southern Tanzania", future_start, form_type="Evaluation")],
        },
        trip_pages={58000: [{"tripdepID": 56807, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    parsed = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).future_trips[0]

    assert parsed.forms_due_count == 0
    assert parsed.forms_badge == "pending"


@pytest.mark.asyncio
async def test_forms_badge_never_claims_complete_when_the_forms_call_fails(monkeypatch):
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start, forms_due=0),
        forms=RuntimeError("forms endpoint down"),
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.has_forms is None
    assert trip.forms_badge is None


@pytest.mark.asyncio
async def test_api_forms_due_alert_survives_a_failed_forms_call(monkeypatch):
    """Degraded path keeps the API's own alert; it only refuses to invent Complete."""
    start = _days_ago(10)
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start, forms_due=2),
        forms=RuntimeError("forms endpoint down"),
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    trip = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert trip.forms_badge == "due"
    assert trip.forms_due_count == 2


@pytest.mark.asyncio
async def test_evaluation_form_is_due_once_the_trip_has_departed(monkeypatch):
    """The other half of the Evaluation rule: after departure it becomes due.

    Receipt_Required is deliberately not consulted for Evaluations — the legacy
    counter does not consult it either.
    """
    start = _days_ago(20)
    trip = _trip(56807, 58000, "Southern Tanzania", _range_string(start))
    trip["formsDue"] = 0
    client = FakeClient(
        homepage={"name": "Wildlife Explorer", "FutureTrips": [], "PastTrips": [trip]},
        forms={
            "requestStatus": "OK",
            "forms": [
                _form("Southern Tanzania", start, form_type="Evaluation", required=False)
            ],
        },
        trip_pages={58000: [{"tripdepID": 56807, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    parsed = (await vendor_service.get_vendor_homepage(123, "WT", "Test")).past_trips[0]

    assert parsed.forms_due_count == 1
    assert parsed.forms_badge == "due"


@pytest.mark.asyncio
async def test_malformed_trip_page_payload_does_not_break_the_page(monkeypatch):
    """An unexpected getTripPage shape degrades that trip to unknown, never 500s."""
    client = FakeClient(
        homepage={
            "name": "African Environments",
            "FutureTrips": [_trip(61689, 10389, "Grand Danube", "September 7-21, 2026")],
            "PastTrips": [],
        },
        trip_pages={10389: [None, "nonsense", {"tripdepID": 61689, "status": "Canceled"}]},
    )
    _install(monkeypatch, client)

    homepage = await vendor_service.get_vendor_homepage(123, "WT", "Test")

    # The junk entries are skipped; the well-formed one still filters the departure.
    assert homepage.future_trips == []


@pytest.mark.asyncio
async def test_trip_page_returning_a_non_dict_leaves_every_trip_visible(monkeypatch):
    class BadClient(FakeClient):
        async def get(self, path, params=None):
            if "/getTripPage/" in path:
                return "not a dict"
            return await super().get(path, params)

    client = BadClient(
        homepage={
            "name": "African Environments",
            "FutureTrips": [_trip(61689, 10389, "Grand Danube", "September 7-21, 2026")],
            "PastTrips": [],
        },
    )
    _install(monkeypatch, client)

    homepage = await vendor_service.get_vendor_homepage(123, "WT", "Test")

    assert [t.trip_departure_id for t in homepage.future_trips] == [61689]


@pytest.mark.asyncio
async def test_one_unparseable_form_does_not_discard_the_others(monkeypatch):
    """A single bad row must not disable the badge for the vendor's whole list."""
    start = _days_ago(10)
    good = _form("Botswana Wildlife Safari", start, required=True)
    bad = {"TripInfo": "Broken - Jan. 1, 2026"}  # no formName -> ValidationError
    client = FakeClient(
        homepage=_homepage_with_past_trip("Botswana Wildlife Safari", start),
        forms={"requestStatus": "OK", "forms": [bad, good]},
        trip_pages={58000: [{"tripdepID": 58152, "status": "Open"}]},
    )
    _install(monkeypatch, client)

    homepage = await vendor_service.get_vendor_homepage(123, "WT", "Test")

    assert len(homepage.forms) == 1
    assert homepage.past_trips[0].forms_badge == "due"


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
            assert vendor_service._parse_trip_start_date(rendered) == day, rendered
