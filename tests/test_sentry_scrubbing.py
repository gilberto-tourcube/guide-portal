"""Tests for app.utils.sentry_scrubbing.

Covers the GUIDE-PORTAL-26 leak class: AuthService.change_password puts the
new password in a URL path segment (V7 API contract we cannot change), so an
httpx.HTTPStatusError's message, and therefore the Sentry event built from
it, carries the cleartext password in multiple places (exception value,
request.url, culprit, transaction, breadcrumbs, stack-frame locals). These
tests assert the scrubber removes the password from every one of those
channels while keeping the surrounding diagnostic text intact.

Fixture password `p4ssw0rd-fixture%@#` is synthetic and must never be
replaced with a real credential.
"""

import json

import httpx
import pytest

from app.utils.sentry_scrubbing import (
    FILTERED,
    redact_text,
    scrub_breadcrumb,
    scrub_event,
)

FIXTURE_PASSWORD = "p4ssw0rd-fixture%@#"


def _assert_no_password(payload) -> str:
    dumped = json.dumps(payload, default=str)
    assert FIXTURE_PASSWORD not in dumped
    return dumped


def test_exception_value_with_password_path_is_scrubbed():
    event = {
        "exception": {
            "values": [
                {
                    "type": "HTTPStatusError",
                    "value": (
                        "Client error '400 Bad Request' for url "
                        "'https://web2.tourcube.net/tourcube/v1/client/851082/"
                        f"password/{FIXTURE_PASSWORD}'\n"
                        "For more information check: "
                        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400"
                    ),
                }
            ]
        }
    }

    result = scrub_event(event, hint=None)

    dumped = _assert_no_password(result)
    assert FILTERED in dumped
    assert "400 Bad Request" in dumped
    assert "client/851082" in dumped
    assert "web2.tourcube.net" in dumped
    assert "developer.mozilla.org" in dumped


def test_request_url_with_password_is_scrubbed():
    event = {
        "request": {
            "url": (
                "https://web2.tourcube.net/tourcube/v1/client/851082/"
                f"password/{FIXTURE_PASSWORD}"
            )
        }
    }

    result = scrub_event(event, hint=None)

    _assert_no_password(result)
    assert result["request"]["url"].endswith(f"password/{FILTERED}")


def test_culprit_and_transaction_are_scrubbed():
    event = {
        "culprit": f"PUT /tourcube/v1/client/851082/password/{FIXTURE_PASSWORD}",
        "transaction": f"/tourcube/v1/client/851082/password/{FIXTURE_PASSWORD}",
    }

    result = scrub_event(event, hint=None)

    dumped = _assert_no_password(result)
    assert FILTERED in dumped


def test_breadcrumb_message_scrubbed_directly_and_via_event():
    crumb = {
        "message": (
            "PUT https://web2.tourcube.net/tourcube/v1/client/851082/"
            f"password/{FIXTURE_PASSWORD} -> 400"
        )
    }

    direct = scrub_breadcrumb(dict(crumb), hint=None)
    assert FIXTURE_PASSWORD not in json.dumps(direct)
    assert FILTERED in direct["message"]

    event = {"breadcrumbs": {"values": [dict(crumb)]}}
    result = scrub_event(event, hint=None)
    dumped = _assert_no_password(result)
    assert FILTERED in dumped


def test_session_cookie_and_cookie_header_are_filtered():
    event = {
        "request": {
            "cookies": {"guide_portal_session": "s%3Aabc123.signature"},
            "headers": {
                "Cookie": "guide_portal_session=s%3Aabc123.signature",
                "Authorization": "Bearer some-token-value",
                "User-Agent": "pytest",
            },
        }
    }

    result = scrub_event(event, hint=None)

    # "cookies" and "Cookie"/"Authorization" all match the sensitive-key
    # substring pattern, so the whole value (dict or string) is replaced.
    assert result["request"]["cookies"] == FILTERED
    assert result["request"]["headers"]["Cookie"] == FILTERED
    assert result["request"]["headers"]["Authorization"] == FILTERED
    # Benign header untouched
    assert result["request"]["headers"]["User-Agent"] == "pytest"


def test_stack_frame_local_var_new_password_is_filtered():
    event = {
        "exception": {
            "values": [
                {
                    "type": "HTTPStatusError",
                    "value": "boom",
                    "stacktrace": {
                        "frames": [
                            {
                                "function": "change_password",
                                "vars": {
                                    "new_password": FIXTURE_PASSWORD,
                                    "client_id": 851082,
                                },
                            }
                        ]
                    },
                }
            ]
        }
    }

    result = scrub_event(event, hint=None)

    frame_vars = result["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert frame_vars["new_password"] == FILTERED
    assert frame_vars["client_id"] == 851082


def test_bool_and_int_values_on_matching_keys_survive():
    event = {
        "extra": {
            "temp_password": True,
            "client_id": 851082,
            "benign_url": "https://web2.tourcube.net/health",
        }
    }

    result = scrub_event(event, hint=None)

    assert result["extra"]["temp_password"] is True
    assert result["extra"]["client_id"] == 851082
    assert result["extra"]["benign_url"] == "https://web2.tourcube.net/health"


def test_query_string_password_param_is_scrubbed():
    text = f"https://web2.tourcube.net/reset?new_password={FIXTURE_PASSWORD}&ok=1"

    result = redact_text(text)

    assert FIXTURE_PASSWORD not in result
    assert f"new_password={FILTERED}" in result
    assert "ok=1" in result


def test_redact_text_idempotent_and_handles_empty_string():
    assert redact_text("") == ""

    text = f"/tourcube/v1/client/851082/password/{FIXTURE_PASSWORD}"
    once = redact_text(text)
    twice = redact_text(once)
    assert once == twice
    assert FIXTURE_PASSWORD not in once


def test_auth_service_log_message_is_safe_after_redact():
    """Mirrors AuthService.change_password's except blocks: str(exc) for an
    httpx.HTTPStatusError contains the full request URL, including the
    password path segment. redact_text must strip it before it reaches
    logger.error (and therefore before it reaches Sentry breadcrumbs)."""
    url = httpx.URL(
        "https://web2.tourcube.net/tourcube/v1/client/851082/"
        f"password/{FIXTURE_PASSWORD}"
    )
    request = httpx.Request("PUT", url)
    response = httpx.Response(400, request=request, text="Bad Request")
    exc = httpx.HTTPStatusError(
        "Client error '400 Bad Request' for url "
        f"'{url}'\nFor more information check: https://developer.mozilla.org/",
        request=request,
        response=response,
    )

    safe = redact_text(str(exc))

    assert FIXTURE_PASSWORD not in safe
    assert FILTERED in safe
    assert "400 Bad Request" in safe


def test_depth_guard_fails_closed():
    """Past the depth guard the scrubber drops the subtree, never forwards it.

    A password buried deeper than _MAX_DEPTH must not be shipped just because
    the recursion gave up: the module's policy is fail closed everywhere.
    """
    from app.utils import sentry_scrubbing

    deep: dict = {"new_password": FIXTURE_PASSWORD}
    for _ in range(sentry_scrubbing._MAX_DEPTH + 5):
        deep = {"nested": deep}

    scrubbed = scrub_event({"extra": deep})

    assert FIXTURE_PASSWORD not in json.dumps(scrubbed, default=str)


def test_realistic_event_nesting_is_not_truncated():
    """The depth guard must sit clear of normal Sentry event nesting."""
    event = {
        "exception": {
            "values": [
                {
                    "type": "HTTPStatusError",
                    "stacktrace": {
                        "frames": [
                            {
                                "function": "change_password",
                                "vars": {
                                    "new_password": FIXTURE_PASSWORD,
                                    "company_config": {"api_url": "https://web2.tourcube.net"},
                                },
                            }
                        ]
                    },
                }
            ]
        }
    }

    scrubbed = scrub_event(event)
    dumped = json.dumps(scrubbed, default=str)

    assert FIXTURE_PASSWORD not in dumped
    # the useful sibling data at the same depth survives
    assert "web2.tourcube.net" in dumped
