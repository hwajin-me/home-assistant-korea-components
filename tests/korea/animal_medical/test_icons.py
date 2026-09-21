"""Semantic icons are shared across medical types and preserve unknown states."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from custom_components.korea_incubator.animal_medical.binary_sensor import (
    MedicalBinarySensor,
)
from custom_components.korea_incubator.animal_medical.compact_sensor import (
    ICONS,
    MedicalInfoSensor,
)
from custom_components.korea_incubator.animal_medical.icons import institution_icon
from custom_components.korea_incubator.animal_medical.schedule_sensor import (
    MedicalTransitionSensor,
)
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor
from custom_components.korea_incubator.pharmacy.sensor import PharmacySensor

from .test_detail_sensor import coordinator
from .test_pharmacy import DATA, RECORD


@pytest.mark.parametrize(
    "state,icon",
    [
        ("open", "mdi:store-check"),
        ("closed", "mdi:store-off"),
        ("break", "mdi:coffee-outline"),
        (None, "mdi:help-circle-outline"),
    ],
)
def test_operating_icons(entry_data, record, state, icon):
    with patch.object(
        AnimalMedicalSensor,
        "native_value",
        new_callable=PropertyMock,
        return_value=state,
    ):
        for primary in (
            AnimalMedicalSensor(coordinator(record), entry_data),
            PharmacySensor(coordinator(RECORD), DATA),
        ):
            assert primary.icon == icon
            assert MedicalInfoSensor(primary, "hours").icon == icon
            for kind in ("open", "break"):
                assert MedicalBinarySensor(primary, kind).icon == icon


@pytest.mark.parametrize(
    "data,icon",
    [
        ({"service": "pharmacy"}, "mdi:pharmacy"),
        ({"institution_type": "pharmacy"}, "mdi:pill"),
        ({"institution_type": "hospital"}, "mdi:paw"),
    ],
)
def test_institution_icons(data, icon):
    assert institution_icon(data) == icon
    assert MedicalInfoSensor(MagicMock(_entry_data=data), "name").icon == icon


def test_information_icons(entry_data, record):
    primary = AnimalMedicalSensor(coordinator(record), entry_data)
    for kind, icon in ICONS.items():
        assert MedicalInfoSensor(primary, kind).icon == icon
    assert MedicalTransitionSensor(primary, "start").icon == "mdi:clock-start"
    assert MedicalTransitionSensor(primary, "end").icon == "mdi:clock-end"


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize(
    "kind,icons",
    [
        ("hours", ("mdi:clock-check-outline", "mdi:clock-alert-outline")),
        ("location", ("mdi:map-marker-check", "mdi:map-marker-question-outline")),
        ("error", ("mdi:alert-circle-outline", "mdi:check-circle-outline")),
    ],
)
def test_diagnostic_icons(kind, icons, active):
    with patch.object(
        MedicalBinarySensor, "is_on", new_callable=PropertyMock, return_value=active
    ):
        assert MedicalBinarySensor(MagicMock(), kind).icon == icons[0 if active else 1]
