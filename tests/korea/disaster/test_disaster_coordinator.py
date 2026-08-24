"""Tests for disaster coordinator filtering."""

from custom_components.korea_incubator.disaster.coordinator import _matches_region


def test_subregion_matches_official_api_name():
    assert _matches_region("서울특별시 용산구", "서울 용산구")


def test_province_aliases_match():
    assert _matches_region("전북특별자치도 전주시", "전북 전주시")
    assert _matches_region("제주특별자치도 제주시", "제주 제주시")


def test_different_district_does_not_match():
    assert not _matches_region("서울특별시 강남구", "서울 용산구")
