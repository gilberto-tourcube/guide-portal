"""Parse the trip date-range strings emitted by the legacy Tourcube API.

The various *Homepage endpoints (getGuideHomepage, getVendorHomepage, ...) send a
human-formatted `dates` string built by the legacy GP_DateString procedure
(tourcube-windev/Tourcube/UtilityProcedures.wdg:5536) instead of a raw start date.
This module is the exact inverse of that procedure, needed whenever the API does not
separately provide a machine-readable departure date (see guide_service, which only
gets `Departure_Date` for PAST trips and must recover the date of FUTURE trips from
this string instead).
"""

import re
from datetime import date, datetime
from typing import Optional

# GP_DateString renders a departure as one of three shapes:
#   same month  -> "September 7-21, 2026"
#   same year   -> "November 22-December 6, 2026"
#   cross year  -> "December 28, 2026-January 5, 2027"
# The cross-year shape must be matched FIRST: a greedy "take the trailing year"
# regex reads it as 2027 and puts the departure a year late.
_CROSS_YEAR_RANGE = re.compile(
    r"^\s*([A-Za-z.]+)\s+(\d{1,2})\s*,\s*(\d{4})\s*-\s*[A-Za-z.]+\s+\d{1,2}\s*,\s*\d{4}\s*$"
)
_SAME_YEAR_RANGE = re.compile(
    r"^\s*([A-Za-z.]+)\s+(\d{1,2})\s*-\s*(?:[A-Za-z.]+\s+)?\d{1,2}\s*,\s*(\d{4})\s*$"
)
# Anything else that still looks like "<Month> <day> ... , <year>" (e.g. a single day).
_LOOSE_RANGE = re.compile(r"^\s*([A-Za-z.]+)\s+(\d{1,2})\b.*,\s*(\d{4})\s*$")


def parse_trip_start_date(trip_dates: Optional[str]) -> Optional[date]:
    """Extract the starting date from trip date ranges like `May 10-20, 2023`."""
    if not trip_dates:
        return None

    for pattern in (_CROSS_YEAR_RANGE, _SAME_YEAR_RANGE, _LOOSE_RANGE):
        match = pattern.match(trip_dates)
        if not match:
            continue

        month, day, year = match.groups()
        normalized = f"{month.rstrip('.')} {day} {year}"

        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(normalized, fmt).date()
            except ValueError:
                continue
    return None
