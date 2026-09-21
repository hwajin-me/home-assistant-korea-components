"""Tests for GasApp amount formatting."""

import pytest

from custom_components.korea_incubator.gasapp.format import parse_charge_amount


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("41000", 41000),
        ("410.00", 41000),
        ("41,000.00", 41000),
        (41000, 41000),
        ("invalid", None),
    ],
)
def test_parse_charge_amount(value, expected):
    """GasApp charge formats must retain their won value."""
    assert parse_charge_amount(value) == expected
