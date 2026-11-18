"""Opening-hours parsing. Anything unexpected becomes unknown (None), never an error."""

import re

from within_reach_pipeline.models import DayHours

_RANGE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-4]):([0-5]\d)$")


def parse_day_hours(value: str) -> DayHours:
    text = value.strip()
    if text.lower() == "closed":
        return ()
    if not text:
        return None
    ranges: list[tuple[str, str]] = []
    for part in re.split(r"[,;]", text):
        match = _RANGE.match(part.strip())
        if match is None:
            return None
        opens = f"{match.group(1)}:{match.group(2)}"
        closes = f"{match.group(3)}:{match.group(4)}"
        ranges.append((opens, closes))
    return tuple(ranges)
