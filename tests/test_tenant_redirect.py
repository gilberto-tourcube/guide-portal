"""Per-tenant redirect switch (INCA V7 -> V8 cutover).

The switch is the ``TENANT_REDIRECTS`` app setting: a JSON object mapping a
company code to the https origin its traffic must be sent to. Empty/unset means
off, and the app must then behave exactly as it did before the switch existed.
"""

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.config import Settings, settings
from app.main import app
from app.services.guide_service import guide_service

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INCA_ORIGIN = "https://inca.guideportal.tourcube.net"
INCA_SWITCH = '{"INCA": "https://inca.guideportal.tourcube.net"}'


@pytest.fixture
def example_tenant_config(monkeypatch):
    """Use the tracked, credential-free tenant matrix for HTTP route tests."""
    monkeypatch.setattr(settings, "api_key_json_path", "config/apikey.json.example")
    monkeypatch.setattr(settings, "_company_configs", None)
    monkeypatch.setattr(settings, "_domain_map", None)
    monkeypatch.setattr(settings, "debug", False)


@pytest.fixture
def switch_on(monkeypatch, example_tenant_config):
    monkeypatch.setattr(settings, "tenant_redirects", INCA_SWITCH)


@pytest.fixture
def switch_off(monkeypatch, example_tenant_config):
    monkeypatch.setattr(settings, "tenant_redirects", "")


@pytest.fixture
def no_guide_hash_lookup(monkeypatch):
    """A redirected guide_hash must never reach the V7 hash lookup."""

    async def _boom(*args, **kwargs):
        raise AssertionError("guide_hash was resolved on V7 for a redirected tenant")

    monkeypatch.setattr(guide_service, "get_guide_id_by_hash", _boom)


# --------------------------------------------------------------------------
# Switch off: behaviour identical to today
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("company_code", ["INCA", "WT", "IG", "MTS"])
async def test_switch_off_serves_every_tenant_as_before(
    secure_client, switch_off, company_code
):
    response = await secure_client.get(
        f"/?company_code={company_code}&mode=Production", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"/auth/login?company_code={company_code}&mode=Production"
    )


@pytest.mark.asyncio
async def test_switch_off_inca_login_link_is_not_redirected(secure_client, switch_off):
    response = await secure_client.get(
        "/auth/login?company_code=INCA&mode=Production", follow_redirects=False
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_switch_off_login_link_without_mode_keeps_todays_400(
    secure_client, switch_off
):
    """Without a mode the generic host answers 400 today; the switch must not alter that."""
    response = await secure_client.get(
        "/auth/login?&company_code=INCA", follow_redirects=False
    )

    assert response.status_code == 400


# --------------------------------------------------------------------------
# Switch on: INCA goes to the V8 host, path and query preserved
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_login_link_is_redirected_with_path_and_query(
    secure_client, switch_on
):
    response = await secure_client.get(
        "/auth/login?&company_code=INCA", follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/auth/login?&company_code=INCA"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["company_code=inca", "company_code=Inca", "companyCode=iNcA", "company_code=%20inca%20"],
)
async def test_company_code_case_and_spelling_do_not_matter(
    secure_client, switch_on, query
):
    response = await secure_client.get(f"/auth/login?{query}", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/auth/login?{query}"


@pytest.mark.asyncio
async def test_camel_case_wins_over_snake_case_like_the_rest_of_the_app(
    secure_client, switch_on
):
    inca_first = await secure_client.get(
        "/auth/login?companyCode=INCA&company_code=WT", follow_redirects=False
    )
    wt_first = await secure_client.get(
        "/auth/login?companyCode=WT&company_code=INCA", follow_redirects=False
    )

    assert inca_first.status_code == 307
    assert wt_first.status_code != 307


@pytest.mark.asyncio
async def test_guide_hash_link_resolving_inca_is_redirected_before_any_lookup(
    secure_client, switch_on, no_guide_hash_lookup
):
    response = await secure_client.get(
        "/guide/home?guide_hash=abc123&company_code=INCA&mode=Production",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        f"{INCA_ORIGIN}/guide/home?guide_hash=abc123&company_code=INCA&mode=Production"
    )


@pytest.mark.asyncio
async def test_root_guide_hash_link_resolving_inca_is_redirected(
    secure_client, switch_on, no_guide_hash_lookup
):
    response = await secure_client.get(
        "/?guideHash=abc123&companyCode=INCA", follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/?guideHash=abc123&companyCode=INCA"


@pytest.mark.asyncio
async def test_post_keeps_its_method_and_body_via_307(secure_client, switch_on):
    response = await secure_client.post(
        "/auth/login?company_code=INCA",
        data={"username": "someone", "password": "x"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/auth/login?company_code=INCA"


@pytest.mark.asyncio
async def test_invalid_mode_does_not_stop_the_redirect(secure_client, switch_on):
    response = await secure_client.get(
        "/auth/login?company_code=INCA&mode=bogus", follow_redirects=False
    )

    assert response.status_code == 307


@pytest.mark.asyncio
async def test_tenant_resolved_only_by_host_is_redirected(
    secure_client, switch_on, monkeypatch
):
    monkeypatch.setattr(settings, "_domain_map", {"inca-v7.example.test": ("INCA", "Production")})
    monkeypatch.setattr(settings, "_company_configs", {})

    response = await secure_client.get(
        "/auth/login", headers={"host": "inca-v7.example.test"}, follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/auth/login"


# --------------------------------------------------------------------------
# Switch on: every other tenant is untouched
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("company_code", ["WT", "IG", "MTS", "SLV", "ARN", "EXC", "BJ", "CTJ", "NOPE"])
async def test_other_tenants_are_not_redirected(secure_client, switch_on, company_code):
    response = await secure_client.get(
        f"/?company_code={company_code}&mode=Production", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"/auth/login?company_code={company_code}&mode=Production"
    )


@pytest.mark.asyncio
async def test_request_without_tenant_keeps_the_neutral_400(secure_client, switch_on):
    response = await secure_client.get("/", follow_redirects=False)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_guide_hash_without_tenant_is_not_redirected(secure_client, switch_on):
    response = await secure_client.get("/?guide_hash=abc123", follow_redirects=False)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_inca_substring_in_other_params_does_not_trigger(secure_client, switch_on):
    response = await secure_client.get(
        "/?company_code=WT&mode=Production&note=INCA", follow_redirects=False
    )

    assert response.status_code == 302


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "PUT", "DELETE"])
async def test_every_method_is_redirected_with_the_same_307(
    secure_client, switch_on, method
):
    response = await secure_client.request(
        method, "/auth/login?company_code=INCA", follow_redirects=False
    )

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/auth/login?company_code=INCA"


# --------------------------------------------------------------------------
# Session: a guide already logged in before the switch was turned on
# --------------------------------------------------------------------------


def _log_in_as(client, session_cookie_factory, company_code):
    client.cookies.set(
        settings.session_cookie_name,
        session_cookie_factory(
            {
                "authenticated": True,
                "user_type": 1,
                "user_role": "Guide",
                "guide_id": 1,
                "company_code": company_code,
                "mode": "Production",
            }
        ),
    )


@pytest.mark.asyncio
async def test_logged_in_inca_guide_without_query_is_redirected(
    secure_client, switch_on, session_cookie_factory
):
    _log_in_as(secure_client, session_cookie_factory, "INCA")

    response = await secure_client.get("/guide/home", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == f"{INCA_ORIGIN}/guide/home"


@pytest.mark.asyncio
async def test_logged_in_guide_of_another_tenant_is_not_redirected(
    secure_client, switch_on, session_cookie_factory
):
    _log_in_as(secure_client, session_cookie_factory, "WT")

    response = await secure_client.get("/guide/home", follow_redirects=False)

    assert response.status_code != 307


@pytest.mark.asyncio
async def test_explicit_company_code_wins_over_the_session_tenant(
    secure_client, switch_on, session_cookie_factory
):
    _log_in_as(secure_client, session_cookie_factory, "INCA")

    response = await secure_client.get(
        "/?company_code=WT&mode=Production", follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login?company_code=WT&mode=Production"


@pytest.mark.asyncio
async def test_session_is_ignored_while_the_switch_is_off(
    secure_client, switch_off, session_cookie_factory
):
    _log_in_as(secure_client, session_cookie_factory, "INCA")

    response = await secure_client.get("/health", follow_redirects=False)

    assert response.status_code == 200
    response = await secure_client.get("/guide/home", follow_redirects=False)
    assert response.status_code != 307


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/health", "/static/css/does-not-matter.css"])
async def test_health_and_static_are_never_redirected(
    secure_client, switch_on, session_cookie_factory, path
):
    _log_in_as(secure_client, session_cookie_factory, "INCA")

    response = await secure_client.get(f"{path}?company_code=INCA", follow_redirects=False)

    assert response.status_code != 307


# --------------------------------------------------------------------------
# Safety: the destination only comes from configuration
# --------------------------------------------------------------------------


async def _raw_get(raw_target: bytes) -> tuple[int, dict]:
    """Drive the ASGI app with a request target httpx would refuse to send."""
    path, _, query = raw_target.partition(b"?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path.decode("latin-1"),
        "raw_path": path,
        "query_string": query,
        "root_path": "",
        "headers": [(b"host", b"guideportal.tourcube.net")],
        "client": ("127.0.0.1", 1234),
        "server": ("guideportal.tourcube.net", 443),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_target",
    [
        b"@evil.example?company_code=INCA",
        b".evil.example?company_code=INCA",
        b":443@evil.example/x?company_code=INCA",
        b"evil.example/x?company_code=INCA",
    ],
)
async def test_request_target_without_leading_slash_cannot_change_the_host(
    switch_on, raw_target
):
    status, headers = await _raw_get(raw_target)

    assert status == 307
    location = urlsplit(headers["location"])
    assert (location.scheme, location.netloc) == ("https", "inca.guideportal.tourcube.net")
    assert location.username is None


@pytest.mark.asyncio
async def test_non_ascii_query_bytes_are_encoded_once(switch_on):
    status, headers = await _raw_get(b"/auth/login?name=\xc3\xa9&company_code=INCA")

    assert status == 307
    assert headers["location"] == f"{INCA_ORIGIN}/auth/login?name=%C3%A9&company_code=INCA"


@pytest.mark.asyncio
async def test_already_encoded_path_and_query_survive_untouched(switch_on):
    status, headers = await _raw_get(b"/a%2Fb/c%20d?x=%C3%A9&company_code=INCA&y=1+2")

    assert status == 307
    assert headers["location"] == f"{INCA_ORIGIN}/a%2Fb/c%20d?x=%C3%A9&company_code=INCA&y=1+2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path_and_query",
    [
        "/auth/login?company_code=INCA&next=https://evil.example&redirect=//evil.example",
        "//evil.example/auth/login?company_code=INCA",
        "/%2F%2Fevil.example/x?company_code=INCA",
        "/auth/login?company_code=INCA&url=http%3A%2F%2Fevil.example",
    ],
)
async def test_destination_never_follows_request_input(
    secure_client, switch_on, path_and_query
):
    response = await secure_client.get(path_and_query, follow_redirects=False)

    assert response.status_code == 307
    location = urlsplit(response.headers["location"])
    assert (location.scheme, location.netloc) == ("https", "inca.guideportal.tourcube.net")


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["host", "x-forwarded-host"])
async def test_spoofed_host_headers_cannot_change_the_destination(
    secure_client, switch_on, header
):
    response = await secure_client.get(
        "/auth/login?company_code=INCA",
        headers={header: "evil.example"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert urlsplit(response.headers["location"]).netloc == "inca.guideportal.tourcube.net"


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["host", "x-forwarded-host"])
async def test_request_already_on_the_target_host_is_not_redirected(
    secure_client, switch_on, header
):
    """No loop once the V8 host is also routed to this app."""
    response = await secure_client.get(
        "/auth/login?company_code=INCA",
        headers={header: "INCA.guideportal.tourcube.net:443"},
        follow_redirects=False,
    )

    assert response.status_code != 307


# --------------------------------------------------------------------------
# Parsing: a bad setting must never take the shared app down
# --------------------------------------------------------------------------


def _parse(raw: str) -> dict:
    return Settings(secret_key="x", tenant_redirects=raw).tenant_redirect_map()


def test_unset_or_blank_switch_is_off():
    assert Settings(secret_key="x").tenant_redirect_map() == {}
    assert _parse("") == {}
    assert _parse("   ") == {}
    assert _parse("{}") == {}


def test_valid_map_is_normalised():
    assert _parse('{" inca ": "https://INCA.guideportal.tourcube.net/"}') == {
        "INCA": INCA_ORIGIN
    }


def test_get_tenant_redirect_is_case_insensitive():
    configured = Settings(secret_key="x", tenant_redirects=INCA_SWITCH)

    assert configured.get_tenant_redirect("inca") == INCA_ORIGIN
    assert configured.get_tenant_redirect(" INCA ") == INCA_ORIGIN
    assert configured.get_tenant_redirect("WT") is None
    assert configured.get_tenant_redirect(None) is None
    assert configured.get_tenant_redirect("") is None


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        '"https://inca.guideportal.tourcube.net"',
        "null",
        "42",
    ],
)
def test_malformed_setting_turns_the_switch_off_instead_of_crashing(raw):
    assert _parse(raw) == {}


@pytest.mark.parametrize(
    "target",
    [
        "http://inca.guideportal.tourcube.net",
        "//inca.guideportal.tourcube.net",
        "inca.guideportal.tourcube.net",
        "javascript:alert(1)",
        "https://",
        "https://inca.guideportal.tourcube.net/some/path",
        "https://inca.guideportal.tourcube.net?x=1",
        "https://inca.guideportal.tourcube.net#frag",
        "https://user:pw@inca.guideportal.tourcube.net",
        "https://inca.guideportal.tourcube.net:notaport",
        "https://exämple.guideportal.tourcube.net",
        "",
        None,
        42,
    ],
)
def test_unsafe_or_malformed_targets_are_dropped(target):
    raw = json.dumps({"INCA": target, "WT": "https://wt.example.test"})

    assert _parse(raw) == {"WT": "https://wt.example.test"}


def test_cache_follows_the_raw_setting():
    configured = Settings(secret_key="x", tenant_redirects=INCA_SWITCH)
    assert configured.get_tenant_redirect("INCA") == INCA_ORIGIN

    configured.tenant_redirects = ""
    assert configured.get_tenant_redirect("INCA") is None

    configured.tenant_redirects = '{"WT": "https://wt.example.test"}'
    assert configured.get_tenant_redirect("INCA") is None
    assert configured.get_tenant_redirect("WT") == "https://wt.example.test"


def test_switch_is_read_from_the_tenant_redirects_environment_variable(monkeypatch):
    monkeypatch.setenv("TENANT_REDIRECTS", INCA_SWITCH)

    assert Settings(secret_key="x").tenant_redirect_map() == {"INCA": INCA_ORIGIN}


@pytest.mark.parametrize("raw", ["{not json", "[]", "null", '{"INCA": "http://insecure.example"}'])
def test_app_still_imports_and_boots_with_a_bad_setting(raw):
    """A bad TENANT_REDIRECTS must not take the shared app down at startup."""
    import os

    code = (
        "import sys; sys.path.insert(0, %r); "
        "from app.main import app; from app.config import settings; "
        "assert settings.tenant_redirect_map() == {}; print('booted')" % str(PROJECT_ROOT)
    )
    env = {
        **os.environ,
        "TENANT_REDIRECTS": raw,
        "SECRET_KEY": "test-secret-key",
        "SENTRY_ENABLED": "false",
        "API_KEY_JSON_PATH": "config/apikey.json.example",
    }

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr[-800:]
    assert "booted" in result.stdout
