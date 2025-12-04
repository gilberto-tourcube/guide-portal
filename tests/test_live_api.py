"""
Live tests that call the real Tourcube API.

These are opt-in to avoid hitting the external API by default. Enable with:
    RUN_TOURCUBE_LIVE=1
and provide credentials via env vars:
    TOURCUBE_GUIDE_USERNAME / TOURCUBE_GUIDE_PASSWORD
    TOURCUBE_VENDOR_USERNAME / TOURCUBE_VENDOR_PASSWORD
Optionally override company/mode:
    TOURCUBE_COMPANY_CODE / TOURCUBE_MODE
"""

import os

import pytest
import pytest_asyncio

from app.config import settings
from app.services.auth_service import auth_service
from app.services.guide_service import guide_service
from app.services.vendor_service import vendor_service

pytestmark = pytest.mark.integration


def _require_live_env() -> dict:
    if os.getenv("RUN_TOURCUBE_LIVE") != "1":
        pytest.skip("Set RUN_TOURCUBE_LIVE=1 to run live Tourcube API tests")
    return {
        "company_code": os.getenv("TOURCUBE_COMPANY_CODE", settings.company_code),
        "mode": os.getenv("TOURCUBE_MODE", settings.mode),
    }


@pytest.fixture
def guide_creds():
    env = _require_live_env()
    username = os.getenv("TOURCUBE_GUIDE_USERNAME")
    password = os.getenv("TOURCUBE_GUIDE_PASSWORD")
    if not username or not password:
        pytest.skip("Set TOURCUBE_GUIDE_USERNAME and TOURCUBE_GUIDE_PASSWORD")
    return {"username": username, "password": password, **env}


@pytest.fixture
def vendor_creds():
    env = _require_live_env()
    username = os.getenv("TOURCUBE_VENDOR_USERNAME")
    password = os.getenv("TOURCUBE_VENDOR_PASSWORD")
    if not username or not password:
        pytest.skip("Set TOURCUBE_VENDOR_USERNAME and TOURCUBE_VENDOR_PASSWORD")
    return {"username": username, "password": password, **env}


@pytest_asyncio.fixture
async def guide_session(guide_creds):
    login = await auth_service.login(
        username=guide_creds["username"],
        password=guide_creds["password"],
        company_code=guide_creds["company_code"],
        mode=guide_creds["mode"],
    )
    assert not login.login_failed, "Guide login failed"
    assert login.type == 1, "Guide login returned unexpected user type"
    homepage = await guide_service.get_guide_homepage(
        guide_id=login.guide_client_id,
        company_code=guide_creds["company_code"],
        mode=guide_creds["mode"],
    )
    return {
        "login": login,
        "homepage": homepage,
        "company_code": guide_creds["company_code"],
        "mode": guide_creds["mode"],
    }


@pytest.mark.asyncio
async def test_live_guide_login_and_homepage(guide_session):
    login = guide_session["login"]
    homepage = guide_session["homepage"]

    assert login.guide_client_id == homepage.guide_id
    assert homepage.future_trips is not None
    assert homepage.forms_pending_count is not None


def _first_trip_from_homepage(homepage):
    trips = list(homepage.future_trips) + list(homepage.past_trips)
    for trip in trips:
        if trip.trip_departure_id and trip.trip_id:
            return trip
    return None


@pytest.mark.asyncio
async def test_live_guide_trip_and_client_data(guide_session):
    login = guide_session["login"]
    homepage = guide_session["homepage"]
    company_code = guide_session["company_code"]
    mode = guide_session["mode"]

    trip = _first_trip_from_homepage(homepage)
    if not trip:
        pytest.skip("No trips available for the guide test account")

    departure = await guide_service.get_trip_departure(
        trip_departure_id=trip.trip_departure_id,
        guide_id=login.guide_client_id,
        company_code=company_code,
        mode=mode,
    )
    assert departure.trip_departure_id == trip.trip_departure_id

    trip_page = await guide_service.get_trip_page(
        trip_id=trip.trip_id,
        guide_id=login.guide_client_id,
        company_code=company_code,
        mode=mode,
    )
    assert trip_page.trip_id == trip.trip_id

    if departure.passengers:
        client = departure.passengers[0]
        client_details = await guide_service.get_client_details(
            client_id=client.client_id,
            guide_id=login.guide_client_id,
            company_code=company_code,
            mode=mode,
        )
        assert client_details.client_id == client.client_id
    else:
        pytest.skip("No passengers available to fetch client details")


@pytest.mark.asyncio
async def test_live_vendor_login_and_homepage(vendor_creds):
    login = await auth_service.login(
        username=vendor_creds["username"],
        password=vendor_creds["password"],
        company_code=vendor_creds["company_code"],
        mode=vendor_creds["mode"],
    )
    if login.login_failed:
        pytest.skip("Vendor login failed; check credentials or API availability")
    assert login.type == 2, "Vendor login returned unexpected user type"
    assert login.guide_vendor_id, "Vendor ID missing from login response"

    homepage = await vendor_service.get_vendor_homepage(
        vendor_id=login.guide_vendor_id,
        company_code=vendor_creds["company_code"],
        mode=vendor_creds["mode"],
    )
    assert homepage.vendor_id == login.guide_vendor_id
    assert homepage.vendor_name

    trips = list(homepage.future_trips) + list(homepage.past_trips)
    if trips and trips[0].trip_id:
        trip_page = await guide_service.get_trip_page(
            trip_id=trips[0].trip_id,
            guide_id=login.guide_vendor_id,  # vendor ID used as guide_id param for API
            company_code=vendor_creds["company_code"],
            mode=vendor_creds["mode"],
        )
        assert trip_page.trip_id == trips[0].trip_id
    else:
        pytest.skip("No vendor trips available to fetch trip page")
