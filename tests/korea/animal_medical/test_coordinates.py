"""Coordinate controls and a complete 25-field API-to-attribute audit."""

from unittest.mock import MagicMock, patch

import pytest
from pyproj.exceptions import ProjError

from custom_components.korea_incubator.animal_medical.coordinates import to_wgs84
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor


@pytest.mark.parametrize(
    "x,y,longitude,latitude",
    [
        (197986.74550655705, 451579.85095634527, 126.978, 37.5665),
        (389004.19066283514, 188683.78154512797, 129.0756, 35.1796),
        (156361.1017044267, 450.9819068313227, 126.5312, 33.4996),
        (200000, 500000, 127.000784, 38.002746),
        ("197,986.74550655705", " 451579.85095634527 ", 126.978, 37.5665),
    ],
)
def test_crs_controls_and_xy_axis_order(x, y, longitude, latitude):
    assert to_wgs84(x, y) == {
        "longitude": pytest.approx(longitude, abs=0.000001),
        "latitude": pytest.approx(latitude, abs=0.000001),
    }


@pytest.mark.parametrize(
    "x,y",
    [
        (None, None),
        ("", ""),
        ("bad", 200000),
        (True, 200000),
        (200000, False),
        ("nan", 200000),
        (200000, "inf"),
        (0, 0),
        (10000000, 10000000),
        (1e300, 1e300),
    ],
)
def test_missing_or_invalid_coordinates_not_shown(x, y):
    assert to_wgs84(x, y) == {}


def test_proj_failure_is_not_an_entity_failure():
    with patch(
        "custom_components.korea_incubator.animal_medical.coordinates._transformer"
    ) as factory:
        factory.return_value.transform.side_effect = ProjError("bad source point")
        assert to_wgs84(200000, 500000) == {}


def test_every_official_record_field_is_exposed(entry_data):
    fields = {
        "OPN_ATMY_GRP_CD": "municipality_code",
        "MNG_NO": "management_number",
        "RGHT_MNBD_SN": "rights_holder_number",
        "DAT_UPDT_SE": "data_update_type",
        "DAT_UPDT_PNT": "data_updated",
        "ROAD_NM_ZIP": "road_postcode",
        "ROAD_NM_ADDR": "road_address",
        "BPLC_NM": "business_name",
        "DTL_SALS_STTS_NM": "detailed_status",
        "DTL_SALS_STTS_CD": "detailed_status_code",
        "LCTN_AREA": "area",
        "SALS_STTS_NM": "operating_status",
        "SALS_STTS_CD": "status_code",
        "LCPMT_YMD": "license_date",
        "LCPMT_RTRCN_YMD": "license_cancelled_date",
        "ROBIZ_YMD": "reopened_date",
        "TELNO": "phone",
        "CRD_INFO_X": "coordinate_x",
        "CRD_INFO_Y": "coordinate_y",
        "LOTNO_ADDR": "lot_number_address",
        "CLSBIZ_YMD": "closed_date",
        "TCBIZ_BGNG_YMD": "suspension_start",
        "TCBIZ_END_YMD": "suspension_end",
        "LCTN_ZIP": "lot_postcode",
        "LAST_MDFCN_PNT": "last_modified",
    }
    data = {key: f"value_{key}" for key in fields}
    data.update(CRD_INFO_X="197986.74550655705", CRD_INFO_Y="451579.85095634527")
    sensor = AnimalMedicalSensor(MagicMock(data=data), entry_data)
    attrs = sensor.extra_state_attributes
    assert len(fields) == 25
    for key, attribute in fields.items():
        assert attrs[attribute] == data[key]
    assert attrs["api_record"] == data
    assert attrs["latitude"] == pytest.approx(37.5665)
    assert attrs["longitude"] == pytest.approx(126.978)
    assert attrs["coordinate_system"] == "EPSG:5174"
    assert attrs["gps_coordinate_system"] == "EPSG:4326"
    assert attrs["location_available"] is True
    assert attrs["open_now"] is None
    assert attrs["opening_hours_available"] is False


def test_missing_gps_removes_old_location_after_update(entry_data):
    coordinator = MagicMock(data={"CRD_INFO_X": 200000, "CRD_INFO_Y": 500000})
    sensor = AnimalMedicalSensor(coordinator, entry_data)
    assert sensor.extra_state_attributes["location_available"]
    coordinator.data = {}
    attrs = sensor.extra_state_attributes
    assert not attrs["location_available"]
    assert "latitude" not in attrs and "longitude" not in attrs
