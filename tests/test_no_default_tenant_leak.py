"""Regression tests for #148.

Every public endpoint must refuse to leak the default tenant
(`settings.company_code` / `settings.mode`) into the response when the
request lacks any resolvable tenant context. A neutral / 400 / error
response is acceptable; a redirect or render that carries the env-var
default tenant's identity is not.
"""

import pytest

from app.config import settings
from app.main import app


# Tenant identity markers that must never appear on an anonymous response.
DEFAULT_COMPANY_CODE = settings.company_code
DEFAULT_TENANT_NAMES = ("Wilderness Travel",)


def _assert_no_default_tenant_leak(response, *, allow_in_query_string: bool = False):
    """Fail loudly if any default-tenant identifier shows up in the response
    body or in a redirect Location header (unless explicitly allowed because
    the caller supplied that tenant in their own query string).
    """
    body = response.text
    assert DEFAULT_COMPANY_CODE not in body, (
        f"Default tenant company_code {DEFAULT_COMPANY_CODE!r} leaked into "
        f"response body. Snippet: {body[:200]!r}"
    )
    for name in DEFAULT_TENANT_NAMES:
        assert name not in body, (
            f"Default tenant name {name!r} leaked into response body."
        )

    if not allow_in_query_string:
        location = response.headers.get("location", "")
        assert DEFAULT_COMPANY_CODE not in location, (
            f"Default tenant {DEFAULT_COMPANY_CODE!r} leaked into Location "
            f"header: {location!r}"
        )


@pytest.mark.asyncio
async def test_root_anonymous_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_auth_login_anonymous_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/auth/login",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_auth_root_anonymous_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/auth/",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_forgot_password_anonymous_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/auth/forgot-password",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_forgot_username_anonymous_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/auth/forgot-username",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_change_password_unauthenticated_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/auth/change-password",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_logout_without_session_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/auth/logout",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_departure_unauthenticated_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/departure/1",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_guide_home_unauthenticated_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/guide/home",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_vendor_home_unauthenticated_does_not_leak_default_tenant(
    secure_client, reset_debug
):
    settings.debug = False
    response = await secure_client.get(
        "/vendor/home",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )
    _assert_no_default_tenant_leak(response)


@pytest.mark.asyncio
async def test_manifest_anonymous_returns_404(
    secure_client, reset_debug
):
    """`GET /manifest.json` without `companyCode` must return 404 (#160).

    After #160, anonymous requests have no install surface — the neutral
    fallback manifest from #148 is replaced by a hard 404. Default-tenant
    identity cannot leak because there is no payload at all.
    """
    settings.debug = False
    response = await secure_client.get("/manifest.json")
    assert response.status_code == 404
    # Body must not contain the default tenant identifiers.
    assert DEFAULT_COMPANY_CODE not in response.text
    for name in DEFAULT_TENANT_NAMES:
        assert name not in response.text


@pytest.mark.asyncio
async def test_manifest_with_tenant_query_non_mobile_returns_404(
    secure_client, reset_debug
):
    """Desktop (non-mobile) requests return 404 even with valid tenant context (#160).

    After #160, only opted-in tenants on mobile UAs receive a manifest.
    Desktop UAs always get 404 regardless of pwa_enabled state.
    """
    settings.debug = False
    # secure_client uses the default TestClient UA, which is not a mobile UA.
    response = await secure_client.get(
        "/manifest.json?companyCode=WTGUIDE&mode=Test"
    )
    assert response.status_code == 404
