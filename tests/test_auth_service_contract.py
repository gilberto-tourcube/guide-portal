"""Contract tests for app.services.auth_service (DEVCUR-1761).

Covers the V7 API method/body contract verified against production
(web2.tourcube.net) in Aug 2026:

    route                                          Allow (real)
    /tourcube/guidePortal/forgotUserName/{email}    POST, PUT
    /tourcube/guidePortal/tempPassword/{email}/{fn} POST
    /tourcube/v1/client/{id}/password/{pwd}         PUT

Before the fix, `send_forgot_username` and `send_temp_password` sent GET
(405 Method Not Allowed in production) and `change_password` interpolated
the raw password into the URL path (a literal `%` broke the path and
returned 400 -- how a guide's password change silently failed while the
portal reported success).

Also covers `_api_business_failure`, the guard against a V7 response that
signals failure inside a 200/40x body instead of via HTTP status.

No test in this file calls the real TourCube API -- httpx.AsyncClient is
replaced with an in-process fake.
"""

import pytest

import app.services.auth_service as svc
from app.config import settings
from app.services.auth_service import _api_business_failure, auth_service


class _FakeResponse:
    def __init__(self, text="ok"):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeClient:
    """Records every call made through it; usable as an async context manager."""

    def __init__(self, calls, response_text="ok"):
        self._calls = calls
        self._response_text = response_text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self._calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return _FakeResponse(self._response_text)

    async def put(self, url, json=None, headers=None):
        self._calls.append({"method": "PUT", "url": url, "json": json, "headers": headers})
        return _FakeResponse(self._response_text)

    async def get(self, url, headers=None):
        self._calls.append({"method": "GET", "url": url, "headers": headers})
        return _FakeResponse(self._response_text)


def _install_fake_client(monkeypatch, calls, response_text="ok"):
    def factory(*args, **kwargs):
        return _FakeClient(calls, response_text)

    monkeypatch.setattr(svc.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_send_forgot_username_posts_json_with_content_type(monkeypatch):
    """Would fail before the fix: the old code called client.get(...) with no
    body, which 405'd against production (Allow: POST, PUT)."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    await auth_service.send_forgot_username(
        email="welcome@zalaz.me", company_code="WT", mode="Test"
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "POST"
    assert call["json"] == {}
    assert call["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_send_forgot_username_percent_encodes_email_in_path(monkeypatch):
    """The email is a URL path segment; its `@` must be percent-encoded so
    the path is well-formed (welcome@zalaz.me -> welcome%40zalaz.me)."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    cfg = settings.get_company_config("WT", "Test")
    await auth_service.send_forgot_username(
        email="welcome@zalaz.me", company_code="WT", mode="Test"
    )

    expected = f"{cfg.api_url}/tourcube/guidePortal/forgotUserName/welcome%40zalaz.me"
    assert calls[0]["url"] == expected


@pytest.mark.asyncio
async def test_send_temp_password_posts_json_with_content_type(monkeypatch):
    """Would fail before the fix: the old code called client.get(...) with no
    body, which 405'd against production (Allow: POST)."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    await auth_service.send_temp_password(
        email="guide@example.com",
        first_name="Guide",
        company_code="WT",
        mode="Test",
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "POST"
    assert call["json"] == {}
    assert call["headers"]["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    "raw_password,expected_segment",
    [
        ("Sup3r%Secret", "Sup3r%25Secret"),
        ("Sup3r+Secret", "Sup3r%2BSecret"),
        ("Sup3r/Secret", "Sup3r%2FSecret"),
        ("Sup3r Secret", "Sup3r%20Secret"),
        ("Sup3rSécret", "Sup3rS%C3%A9cret"),
    ],
)
@pytest.mark.asyncio
async def test_change_password_percent_encodes_special_characters(
    monkeypatch, raw_password, expected_segment
):
    """Would fail before the fix: the raw password was interpolated straight
    into the URL path, so a `%` (or other reserved character) in the
    password broke the path -- production returned 400 for `%` while the
    portal still reported success to the guide.

    Passwords used here are fictitious placeholders for character-class
    coverage, never a real credential.
    """
    calls = []
    _install_fake_client(monkeypatch, calls)

    cfg = settings.get_company_config("WT", "Test")
    result = await auth_service.change_password(
        client_id=850669,
        new_password=raw_password,
        company_code="WT",
        mode="Test",
    )

    assert result is True
    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "PUT"
    assert call["json"] == {}
    expected_url = f"{cfg.api_url}/tourcube/v1/client/850669/password/{expected_segment}"
    assert call["url"] == expected_url
    # The raw (unencoded) password must never appear verbatim in the URL.
    if raw_password != expected_segment:
        assert raw_password not in call["url"]


class TestApiBusinessFailure:
    """`_api_business_failure` is the guard against a V7 "false success":
    the API can return HTTP 200 (or a non-error 40x) while the body itself
    says the operation failed."""

    def test_access_denied_body_is_a_failure(self):
        assert _api_business_failure("Access Denied") is not None

    def test_status_3_in_json_list_is_a_failure(self):
        body = '[{"Response":{"status":"3"}}]'
        failure = _api_business_failure(body)
        assert failure is not None
        assert "3" in failure

    def test_status_1_in_json_list_is_success(self):
        body = '[{"Response":{"status":"1"}}]'
        assert _api_business_failure(body) is None

    def test_status_1_as_int_is_success(self):
        body = '[{"Response":{"status":1}}]'
        assert _api_business_failure(body) is None

    def test_empty_body_is_not_a_failure(self):
        assert _api_business_failure("") is None

    def test_non_json_body_is_not_a_failure(self):
        """A plain-text success body (no Response.status at all) must not be
        misread as failure -- this preserves current behavior for endpoints
        whose success body isn't JSON."""
        assert _api_business_failure("Email sent successfully") is None

    def test_json_object_without_response_key_is_not_a_failure(self):
        assert _api_business_failure('{"ok": true}') is None


@pytest.mark.asyncio
async def test_send_forgot_username_raises_on_business_failure_without_leaking_body(
    monkeypatch
):
    """A 200 OK carrying a V7 business failure must surface as an
    httpx.HTTPError (so existing route error-handling kicks in) instead of
    being reported as success."""
    calls = []
    _install_fake_client(monkeypatch, calls, response_text='[{"Response":{"status":"3"}}]')

    import httpx

    with pytest.raises(httpx.HTTPError):
        await auth_service.send_forgot_username(
            email="welcome@zalaz.me", company_code="WT", mode="Test"
        )


@pytest.mark.asyncio
async def test_change_password_raises_on_business_failure_and_error_excludes_password(
    monkeypatch
):
    """The raised error message must never contain the password itself."""
    calls = []
    _install_fake_client(monkeypatch, calls, response_text='[{"Response":{"status":"4"}}]')

    import httpx

    secret_password = "TotallyFakeTestPassword123"
    with pytest.raises(httpx.HTTPError) as exc_info:
        await auth_service.change_password(
            client_id=850669,
            new_password=secret_password,
            company_code="WT",
            mode="Test",
        )

    assert secret_password not in str(exc_info.value)


class TestNotFoundIsNotAnEnumerationOracle:
    """Status 4 ("record not found") must not leak account existence.

    The public forgot-username / forgot-password forms would otherwise
    answer "this address exists" vs "it doesn't" for anyone who asked.
    Password change keeps the strict reading: a silent "not found" there is
    the false success this guard exists to prevent.
    """

    def test_status_4_is_a_failure_by_default(self):
        body = '[{"Response":{"status":"4"}}]'
        assert _api_business_failure(body) is not None

    def test_status_4_is_success_when_not_found_is_tolerated(self):
        body = '[{"Response":{"status":"4"}}]'
        assert (
            _api_business_failure(body, treat_not_found_as_failure=False) is None
        )

    def test_invalid_api_key_still_fails_when_not_found_is_tolerated(self):
        body = '[{"Response":{"status":"3"}}]'
        assert (
            _api_business_failure(body, treat_not_found_as_failure=False)
            is not None
        )


@pytest.mark.asyncio
async def test_send_forgot_username_stays_silent_on_unknown_address(monkeypatch):
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"4"}}]'
    )

    # Must not raise: an unknown address looks exactly like a known one.
    await auth_service.send_forgot_username(
        email="zz-nobody@example.invalid", company_code="WT", mode="Production"
    )
    assert calls[0]["method"] == "POST"


@pytest.mark.asyncio
async def test_send_temp_password_stays_silent_on_unknown_address(monkeypatch):
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"4"}}]'
    )

    await auth_service.send_temp_password(
        email="zz-nobody@example.invalid",
        first_name="Zzprobe",
        company_code="WT",
        mode="Production",
    )
    assert calls[0]["method"] == "POST"
