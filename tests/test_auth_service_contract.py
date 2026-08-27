"""Contract tests for app.services.auth_service (DEVCUR-1761).

Covers the V7 API method/body contract verified against test AND production
in Aug 2026:

    route                                              verb   result
    /tourcube/guidePortal/forgotUserName/{email}        POST   500 (both envs)
    /tourcube/guidePortal/tempPassword/{email}/{fn}     POST   500 (both envs)
    /tourcube/v1/client/retrievePortalUsername/{email}  GET    200 (works)
    /tourcube/v1/client/resetPassword/{username}        GET    200 (works)
    /tourcube/v1/client/{id}/password/{pwd}             PUT    (unrelated, works)

The two `guidePortal` routes crash *inside* the API on both environments
(HTTP 500, "Wrong constant passed as parameter", error 70501 -- an
`HReadFirst(Brand, BrandID, Company_control.DefaultBrand)` that blows up
before the API even looks at our parameter). `send_forgot_username` and
`request_password_reset` (formerly `send_temp_password`) now call the
working `v1/client` equivalents instead, over GET with no body.

`change_password` still interpolates the raw password into the URL path
and must percent-encode it (a literal `%` broke the path and returned 400
-- how a guide's password change silently failed while the portal reported
success).

Also covers `_api_business_failure`, the guard against a V7 response that
signals failure inside a 200/40x body instead of via HTTP status.

No test in this file calls the real TourCube API -- httpx.AsyncClient is
replaced with an in-process fake.
"""

import pytest

import app.services.auth_service as svc
from app.config import settings
from app.services.auth_service import _api_business_failure, auth_service


def _fake_capture_message_with_context(monkeypatch):
    """Replace capture_message_with_context with a recording stub; returns
    the list of (args, kwargs) call records."""
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(svc, "capture_message_with_context", fake)
    return calls


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
async def test_send_forgot_username_gets_client_retrieve_portal_username(monkeypatch):
    """Would fail if this route regresses back to `guidePortal/forgotUserName`:
    that route crashes inside the API (500) on both test and production
    (DEVCUR-1761). The working replacement is a plain GET, no body, no
    Content-Type header."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    cfg = settings.get_company_config("WT", "Test")
    await auth_service.send_forgot_username(
        email="welcome@zalaz.me", company_code="WT", mode="Test"
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "GET"
    expected = (
        f"{cfg.api_url}/tourcube/v1/client/retrievePortalUsername/"
        "welcome%40zalaz.me"
    )
    assert call["url"] == expected
    assert call["headers"]["tc-api-key"] == cfg.api_key
    assert "Content-Type" not in (call["headers"] or {})


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

    expected = (
        f"{cfg.api_url}/tourcube/v1/client/retrievePortalUsername/"
        "welcome%40zalaz.me"
    )
    assert calls[0]["url"] == expected


@pytest.mark.asyncio
async def test_request_password_reset_gets_client_reset_password(monkeypatch):
    """Would fail if this route regresses back to `guidePortal/tempPassword`:
    that route crashes inside the API (500) on both test and production
    (DEVCUR-1761). The working replacement is a plain GET keyed on the
    PORTAL USERNAME (not email/first name), no body, no Content-Type
    header."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    cfg = settings.get_company_config("WT", "Test")
    await auth_service.request_password_reset(
        portal_user_name="jsmith",
        company_code="WT",
        mode="Test",
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "GET"
    expected = f"{cfg.api_url}/tourcube/v1/client/resetPassword/jsmith"
    assert call["url"] == expected
    assert call["headers"]["tc-api-key"] == cfg.api_key
    assert "Content-Type" not in (call["headers"] or {})


@pytest.mark.asyncio
async def test_request_password_reset_percent_encodes_username_in_path(monkeypatch):
    """The username is a URL path segment; reserved characters must be
    percent-encoded so the path stays well-formed."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    cfg = settings.get_company_config("WT", "Test")
    await auth_service.request_password_reset(
        portal_user_name="jo ann/smith",
        company_code="WT",
        mode="Test",
    )

    expected = f"{cfg.api_url}/tourcube/v1/client/resetPassword/jo%20ann%2Fsmith"
    assert calls[0]["url"] == expected


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
    says the operation failed. It returns an `ApiFailure(status,
    description)` NamedTuple, or `None` when nothing positively indicates
    failure -- the (status, description) split lets callers decide *how*
    to react to a given status without re-parsing the description string.
    """

    def test_access_denied_body_is_a_failure(self):
        failure = _api_business_failure("Access Denied")
        assert failure is not None
        assert failure.status == "3"

    def test_status_3_in_json_list_is_a_failure(self):
        body = '[{"Response":{"status":"3"}}]'
        failure = _api_business_failure(body)
        assert failure is not None
        assert failure.status == "3"
        assert "3" in failure.description

    def test_status_4_in_json_list_is_a_failure(self):
        """The helper is strict -- it always reports status 4 ("record not
        found"); tolerating it is a decision made at each call site, not
        inside this helper (see DEVCUR-1761)."""
        body = '[{"Response":{"status":"4"}}]'
        failure = _api_business_failure(body)
        assert failure is not None
        assert failure.status == "4"

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
    """The `v1/client` recovery routes (DEVCUR-1761) report status "2" for
    "not found" (a different meaning than the legacy `guidePortal` family's
    status 2 -- see the note on `_V7_RESPONSE_STATUS_MESSAGES`). Status "2"
    must not leak account existence to the *user*, but must never go
    unnoticed by *us*.

    The public forgot-username / forgot-password forms tolerate status "2"
    (and any other business status besides "3"/Access Denied): the user
    still sees success, but the service always logs it and reports it to
    Sentry. Password change keeps the strict reading (untouched by this
    ticket): a silent "not found" there is the false success that guard
    exists to prevent, so it raises like any other failure.
    """

    def test_status_2_is_reported_by_the_helper(self):
        body = '[{"Response":{"status":"2"}}]'
        failure = _api_business_failure(body)
        assert failure is not None
        assert failure.status == "2"


@pytest.mark.asyncio
async def test_send_forgot_username_stays_silent_on_status_2_but_reports_to_sentry(
    monkeypatch
):
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"2"}}]'
    )
    sentry_calls = _fake_capture_message_with_context(monkeypatch)

    # Must not raise: an unknown address looks exactly like a known one to
    # the user calling this...
    await auth_service.send_forgot_username(
        email="zz-nobody@example.invalid", company_code="WT", mode="Production"
    )
    assert calls[0]["method"] == "GET"

    # ...but we must still know it happened.
    assert len(sentry_calls) == 1


@pytest.mark.asyncio
async def test_request_password_reset_stays_silent_on_status_2_but_reports_to_sentry(
    monkeypatch
):
    """Status "2" is also what a vendor's username gets back (the procedure
    looks the username up against the client table) -- same tolerate-and-
    report policy applies regardless of why the account isn't eligible."""
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"2"}}]'
    )
    sentry_calls = _fake_capture_message_with_context(monkeypatch)

    await auth_service.request_password_reset(
        portal_user_name="zzprobe",
        company_code="WT",
        mode="Production",
    )
    assert calls[0]["method"] == "GET"
    assert len(sentry_calls) == 1


@pytest.mark.asyncio
async def test_send_forgot_username_access_denied_still_raises_and_skips_sentry_message(
    monkeypatch
):
    """Only the infrastructure/config failure (Access Denied, status "3")
    keeps raising; it goes through capture_exception_with_context (via the
    except block) rather than capture_message_with_context."""
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"3"}}]'
    )
    sentry_calls = _fake_capture_message_with_context(monkeypatch)

    import httpx

    with pytest.raises(httpx.HTTPError):
        await auth_service.send_forgot_username(
            email="welcome@zalaz.me", company_code="WT", mode="Test"
        )
    assert sentry_calls == []


@pytest.mark.asyncio
async def test_request_password_reset_access_denied_still_raises_and_skips_sentry_message(
    monkeypatch
):
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"3"}}]'
    )
    sentry_calls = _fake_capture_message_with_context(monkeypatch)

    import httpx

    with pytest.raises(httpx.HTTPError):
        await auth_service.request_password_reset(
            portal_user_name="welcome",
            company_code="WT",
            mode="Test",
        )
    assert sentry_calls == []


@pytest.mark.asyncio
async def test_change_password_raises_on_status_4_not_found(monkeypatch):
    """Unlike the email flows, change_password never tolerates status 4 --
    a silent "not found" there is exactly the false success this guard was
    built to prevent (see the module docstring)."""
    calls = []
    _install_fake_client(
        monkeypatch, calls, response_text='[{"Response":{"status":"4"}}]'
    )

    import httpx

    with pytest.raises(httpx.HTTPError):
        await auth_service.change_password(
            client_id=850669,
            new_password="TotallyFakeTestPassword123",
            company_code="WT",
            mode="Test",
        )
