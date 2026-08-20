"""Defensive Sentry payload scrubbing (GUIDE-PORTAL-26).

Why this module exists
-----------------------
`AuthService.change_password` (app/services/auth_service.py) calls the V7
TourCube API with the new password as a URL PATH SEGMENT:

    {api_url}/tourcube/v1/client/{client_id}/password/{new_password}

That is the API's contract; it is owned by a separate WinDev component and
cannot be changed from this repo. When the call fails, `httpx` builds its
`HTTPStatusError` message from the full request URL, so the cleartext
password ends up in:

- the exception's `value` (and therefore the Sentry issue title),
- `request.url`,
- `culprit` / `transaction` (derived from the path),
- logging breadcrumbs (our own `logger.error(..., e)` calls stringify `e`),
- captured stack-frame local variables (the `new_password` local itself).

sentry-sdk 2.48.0's built-in `EventScrubber` does NOT cover any of this. Two
specific gaps, verified against the installed source:

1. `EventScrubber` is always active regardless of `send_default_pii`, but its
   `scrub_dict` only redacts a key when `key.lower()` is an EXACT match
   against its denylist. `new_password` and `guide_portal_session` are not
   in that denylist and are not exact matches for entries that are, so they
   pass through untouched.
2. Nothing in the built-in scrubber inspects `exception.values[].value`,
   `message`, `logentry`, `request.url`, `culprit`, `transaction`, or
   breadcrumb `message` strings at all -- it only walks a fixed set of
   structured fields (extra, contexts, request.data, etc). A password
   embedded in free text (like an exception message) is invisible to it.

This module plugs both gaps with a `before_send` / `before_breadcrumb` pair
that recursively walks the whole payload, redacting by substring key match
(catching `new_password`, `tc-api-key`, `guide_portal_session`, ...) and by
regex over free-text strings (catching the password sitting in a URL path,
a query string, or a stringified exception message).

Fail-closed policy
------------------
If scrubbing itself raises for any reason, we do not fall back to sending
the original, unscrubbed event -- an event we failed to clean might still
carry a secret. `scrub_event` logs a warning and returns `None`, which tells
the Sentry SDK to drop the event entirely. Losing one error report is an
acceptable cost; leaking a password to a third-party service is not.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

FILTERED = "[Filtered]"

# Fallback session cookie name(s), used in addition to
# settings.session_cookie_name so this module still protects even if
# app.config's import order or defaults ever change.
_FALLBACK_COOKIE_NAMES = ("guide_portal_session",)

try:
    from app.config import settings as _settings

    _COOKIE_NAMES = tuple(
        dict.fromkeys(
            (_settings.session_cookie_name, *_FALLBACK_COOKIE_NAMES)
        )
    )
except Exception:  # pragma: no cover - defensive, config import shouldn't fail
    _COOKIE_NAMES = _FALLBACK_COOKIE_NAMES

_MAX_DEPTH = 30

# 1. Secret-bearing path segment. The password is the LAST path segment and
# the raw f-string in auth_service.py does not URL-encode it, so it may
# legitimately contain '%', '@', '#', '?', '/' etc. We therefore redact
# everything up to the next whitespace/quote/angle-bracket rather than
# stopping at the next '/', '?' or '#' -- those characters can be part of
# the secret itself.
_PATH_SECRET_RE = re.compile(
    r"(/(?:password|passwd|pwd|temp-password|temp_password)/)"
    r"[^\s'\"<>]*",
    re.IGNORECASE,
)

# 2. Secret query parameter.
_QUERY_SECRET_RE = re.compile(
    r"([?&](?:new_|confirm_|old_|current_)?(?:password|passwd|pwd)=)"
    r"[^&\s'\"<>]*",
    re.IGNORECASE,
)

# 3. Session cookie value appearing inline in free text (e.g. a raw
# Cookie header string, or a log line that dumped headers).
_COOKIE_NAME_ALTERNATION = "|".join(re.escape(name) for name in _COOKIE_NAMES)
_COOKIE_VALUE_RE = re.compile(
    rf"\b({_COOKIE_NAME_ALTERNATION})=[^\s;'\"]*",
    re.IGNORECASE,
)

# Keys whose values are considered sensitive by substring match (case
# insensitive). This is deliberately broader than sentry-sdk's exact-match
# denylist: it is what catches `new_password`, `tc-api-key`,
# `guide_portal_session`, `confirm_password`, etc.
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|apikey|credential|"
    r"cookie|session|authorization)",
    re.IGNORECASE,
)


def redact_text(value: str) -> str:
    """Redact secrets embedded in free-text strings (URLs, log lines, etc).

    Applies, in order: password/temp-password path segments, password query
    parameters, and inline session cookie values. Safe to call repeatedly --
    once a segment is replaced with FILTERED it no longer matches.
    """
    if not value:
        return value

    result = _PATH_SECRET_RE.sub(lambda m: m.group(1) + FILTERED, value)
    result = _QUERY_SECRET_RE.sub(lambda m: m.group(1) + FILTERED, result)
    result = _COOKIE_VALUE_RE.sub(lambda m: m.group(1) + "=" + FILTERED, result)
    return result


def _redact_value(value: Any, depth: int) -> Any:
    """Redact a value already known to sit under a sensitive key."""
    if isinstance(value, (str, bytes, dict, list)):
        return FILTERED
    # bool/int/float/None (and anything else) survive untouched -- e.g. the
    # useful `temp_password: true` debug flag.
    return value


def _scrub(node: Any, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        # Fail closed, consistent with the module policy: past the depth
        # guard we can no longer promise the subtree was inspected, so we
        # drop its contents instead of forwarding them. Real Sentry events
        # nest to roughly 10 levels (event > exception > values > stacktrace
        # > frames > vars > ...), so this only fires on pathological or
        # self-referential payloads.
        return _redact_value(node, depth)

    if isinstance(node, dict):
        scrubbed = {}
        for key, value in node.items():
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                scrubbed[key] = _redact_value(value, depth + 1)
            else:
                scrubbed[key] = _scrub(value, depth + 1)
        return scrubbed

    if isinstance(node, list):
        return [_scrub(item, depth + 1) for item in node]

    if isinstance(node, str):
        return redact_text(node)

    # bytes, bool, int, float, None, AnnotatedValue, etc: unchanged.
    return node


def scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    """Sentry `before_send` hook: recursively scrub an outgoing event.

    Returns the mutated event, or `None` to drop the event entirely if
    scrubbing fails unexpectedly -- see module docstring for the rationale
    (fail closed rather than risk shipping an unscrubbed secret).
    """
    try:
        return _scrub(event, 0)
    except Exception:
        logger.warning(
            "sentry_scrubbing.scrub_event failed; dropping event rather than "
            "risk sending unscrubbed data",
            exc_info=True,
        )
        return None


def scrub_breadcrumb(crumb: dict, hint: dict | None = None) -> dict | None:
    """Sentry `before_breadcrumb` hook: recursively scrub a breadcrumb.

    Same fail-closed policy as `scrub_event`: on unexpected failure the
    breadcrumb is dropped rather than forwarded unscrubbed.
    """
    try:
        return _scrub(crumb, 0)
    except Exception:
        logger.warning(
            "sentry_scrubbing.scrub_breadcrumb failed; dropping breadcrumb "
            "rather than risk sending unscrubbed data",
            exc_info=True,
        )
        return None
