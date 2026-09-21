"""Public Kakao review/photo previews, privacy filtering and entity rendering."""

from copy import deepcopy

import pytest

from custom_components.korea_incubator.animal_medical.detail_sensor import (
    MedicalDetailSensor,
    fields,
)
from custom_components.korea_incubator.animal_medical.kakao import async_place
from custom_components.korea_incubator.animal_medical.media import (
    photo_url,
    public_media,
)
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor

from .test_detail_sensor import coordinator
from .test_kakao import session_for


def payload():
    return {
        "summary": {
            "confirm_id": "123",
            "main_photo_url": "http://t1.daumcdn.net/photo?original",
        },
        "photos": {
            "counts": {"total": 12},
            "photos": [
                {
                    "url": "https://t1.daumcdn.net/photo?original",
                    "meta": {"user": "PRIVATE"},
                },
                {"url": "https://img.kakaocdn.net/other", "author": "PRIVATE"},
            ],
        },
        "kakaomap_review": {
            "score_set": {"average_score": 4.5, "review_count": 8},
            "has_next": True,
            "reviews": [
                {
                    "status": "S",
                    "contents": "공개 리뷰",
                    "star_rating": 5,
                    "registered_at": "2026-09-21",
                    "meta": {"author": "PRIVATE"},
                }
            ],
        },
    }


def test_public_previews_and_no_profiles():
    data = payload()
    original = deepcopy(data)
    result = public_media(data, "123")
    assert data == original
    assert result["rating"] == 4.5 and result["review_count"] == 8
    assert result["photo_count"] == 12
    assert result["reviews"] == [
        {"text": "공개 리뷰", "rating": 5, "date": "2026-09-21"}
    ]
    assert result["photos"] == [
        "https://t1.daumcdn.net/photo?original",
        "https://img.kakaocdn.net/other",
    ]
    assert result["reviews_has_more"]
    assert "PRIVATE" not in str(result)


def test_restrictions_remove_even_present_content():
    data = payload()
    data["restrict"] = {
        "review_read": {"is_restrict": True},
        "photo": {"is_restrict": True},
    }
    result = public_media(data, "123")
    assert result["reviews"] == result["photos"] == []
    assert result["main_photo"] is result["rating"] is result["photo_count"] is None
    assert result["reviews_restricted"] and result["photos_restricted"]


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://evil.test/image",
        "javascript:alert(1)",
        "https://daumcdn.net.evil.test/image",
        "https://user:password@t1.daumcdn.net/image",
        "https://t1.daumcdn.net:9000/image",
        "https://t1.daumcdn.net:bad/image",
        "https://[invalid/image",
        "x" * 2049,
    ],
)
def test_unsafe_photo_urls(url):
    assert photo_url(url) is None


def test_photo_fallback_and_preview_limits():
    data = payload()
    data["summary"] = {}
    data["photos"]["photos"] = [
        {"url": f"http://t1.daumcdn.net/{n}"} for n in range(30)
    ]
    data["kakaomap_review"]["reviews"] *= 8
    data["kakaomap_review"]["reviews"][0]["contents"] = "가" * 800
    data["kakaomap_review"]["has_next"] = False
    result = public_media(data, "123")
    assert result["main_photo"] == "https://t1.daumcdn.net/0"
    assert len(result["photos"]) == 10
    assert len(result["reviews"]) == 5
    assert len(result["reviews"][0]["text"]) == 500
    assert result["reviews_has_more"]


@pytest.mark.parametrize(
    "value", [None, "bad", True, -1, float("nan"), float("inf"), 6.5]
)
def test_invalid_metrics(value):
    result = public_media(
        {
            "kakaomap_review": {"score_set": {"average_score": value}},
            "photos": {"counts": {"total": 1.5}},
        },
        "123",
    )
    assert result["rating"] is None
    assert result["photo_count"] is None


def test_invalid_optional_sections_and_private_status():
    result = public_media(
        {
            "photos": [],
            "kakaomap_review": {
                "reviews": [
                    None,
                    {"contents": "deleted", "status": "D"},
                    {"status": "S", "contents": None},
                ]
            },
            "restrict": [],
        },
        "123",
    )
    assert result["reviews"] == result["photos"] == []
    assert result["rating"] is None
    assert not result["reviews_has_more"]
    assert public_media({}, "123")["main_photo"] is None


@pytest.mark.asyncio
async def test_real_place_pipeline_normalizes_and_enforces_restriction():
    data = payload()
    result = await async_place(session_for((200, data)), "123")
    assert result["summary"]["main_photo_url"].startswith("https://")
    assert "PRIVATE" not in str(result)
    data["restrict"] = {"photo": {"is_restrict": True}}
    result = await async_place(session_for((200, data)), "123")
    assert result["summary"]["main_photo_url"] is None


def test_entities_and_thumbnail(entry_data, record):
    media = public_media(payload(), "123")
    primary = AnimalMedicalSensor(
        coordinator({**record, "_kakao": {"media": media}}), entry_data
    )
    available = fields(primary)
    assert available[("media", "rating")] == ("카카오 평점", 4.5)
    for key in media:
        sensor = MedicalDetailSensor(primary, ("media", key), "카카오 정보")
        assert sensor.extra_state_attributes["value"] == media[key]
        if key == "main_photo":
            assert sensor.entity_picture == media[key]
        else:
            assert sensor.entity_picture is None
