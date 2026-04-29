"""Display formatters used by Jinja2 templates."""

import re
from typing import Optional

_DIGITS_RE = re.compile(r"\D+")


def format_us_phone(value: Optional[str]) -> str:
    """Format a US phone number for display.

    Strips non-digit characters then groups the digits:
    - 10 digits           → "(NNN) NNN-NNNN"
    - 11 digits, leading 1 → "+1 (NNN) NNN-NNNN"
    - anything else        → return the original string unchanged

    `None` and empty input return an empty string.
    """
    if not value:
        return ""

    raw = str(value)
    digits = _DIGITS_RE.sub("", raw)

    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:11]}"

    return raw


def format_destination(value: Optional[str]) -> str:
    """Format a comma-joined destination string with ", " separators.

    The TourCube API returns destinations as a comma-joined string with no
    spaces (e.g. ``"Europe,Switzerland,Alps"``). This filter splits the string,
    strips each segment, and rejoins with ``", "`` so the UI shows clean
    breadcrumbs (``"Europe, Switzerland, Alps"``).

    Idempotent on properly formatted input (already-spaced commas are kept).
    `None` or empty input returns an empty string.
    """
    if not value:
        return ""

    parts = [segment.strip() for segment in str(value).split(",")]
    parts = [segment for segment in parts if segment]

    return ", ".join(parts)
