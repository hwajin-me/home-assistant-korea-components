"""Formatting helpers for values returned by the GasApp API."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_charge_amount(value: Any) -> int | None:
    """Return a GasApp charge amount in won.

    GasApp normally returns a plain won amount (``"41000"``), but some gas
    companies return the same amount in a two-part display format
    (``"410.00"`` for 41,000 won).  That dot is a formatting separator, not
    a decimal fraction of a won.  Locale-formatted values such as
    ``"41,000.00"`` retain their conventional meaning.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            amount = int(value)
        except (OverflowError, ValueError):
            return None
        # JSON numbers do not retain trailing zeroes: the API's ``410.00``
        # arrives as ``410.0``.  A non-zero city-gas bill below 1,000 won is
        # this compact hundred-won format, not a 410-won bill.
        return amount * 100 if 0 < amount < 1000 else amount
    if not isinstance(value, str):
        return None

    amount = value.strip().replace("원", "").strip()
    if not amount:
        return None

    # Some companies use a dot to split the hundred-won portion, e.g. 410.00.
    compact_match = re.fullmatch(r"(\d{1,3})\.(\d{2})", amount)
    if compact_match:
        return int("".join(compact_match.groups()))

    # A comma makes the dot a conventional decimal suffix: 41,000.00.
    normalized = amount.replace(",", "")
    try:
        return int(Decimal(normalized))
    except (InvalidOperation, ValueError):
        return None
