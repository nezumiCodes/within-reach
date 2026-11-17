"""Postcode normalisation and Northern Ireland exclusion.

Northern Ireland (BT) postcodes are excluded from every published file because their
ONSPD rows are licensed for internal business use only (spec C3, FR-04).
"""

import re

# Outward code: A9, A99, AA9, AA99, A9A or AA9A. Inward code: 9AA. Plus the special GIR 0AA.
_POSTCODE = re.compile(r"^(?:([A-Z]{1,2}[0-9][A-Z0-9]?)([0-9][A-Z]{2})|(GIR)(0AA))$")


def normalise_postcode(raw: str) -> str | None:
    """Return the postcode in upper case with a single space, or None if it isn't valid."""
    compact = re.sub(r"\s+", "", raw).upper()
    match = _POSTCODE.match(compact)
    if match is None:
        return None
    outward = match.group(1) or match.group(3)
    inward = match.group(2) or match.group(4)
    return f"{outward} {inward}"


def is_northern_ireland(postcode: str) -> bool:
    """True for BT postcodes, which must never be published."""
    return re.sub(r"\s+", "", postcode).upper().startswith("BT")
