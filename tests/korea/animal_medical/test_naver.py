"""Naver observed page schema, safe URLs, holiday precedence and display fixes."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.animal_medical import naver
from custom_components.korea_incubator.animal_medical.compact_sensor import (
    MedicalInfoSensor,
)
from custom_components.korea_incubator.animal_medical.hours import (
    SEOUL,
    effective_schedule,
    today_hours,
)
from custom_components.korea_incubator.animal_medical.media import (
    photo_url,
    public_media,
)

STAMP = datetime(2026, 9, 21, 12, tzinfo=SEOUL)


@pytest.mark.asyncio
async def test_transport_and_no_retry():
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"ok": True})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    session = MagicMock()
    session.get.return_value = context
    assert await naver._get(session, "https://map.naver.com/", json_response=True) == {
        "ok": True
    }
    assert session.get.call_args.kwargs["headers"]["Accept"] == "application/json"

    async def chunks(_size):
        yield b"hello "
        yield b"world"

    response.content.iter_chunked = chunks
    assert await naver._get(session, "https://map.naver.com/") == "hello world"
    headers = session.get.call_args.kwargs["headers"]
    assert headers == naver.DOCUMENT_HEADERS
    assert "Chrome/" in headers["User-Agent"]
    assert headers["Accept-Language"].startswith("ko")
    assert "text/html" in headers["Accept"]
    assert not any("cookie" in key.lower() or "token" in key.lower() for key in headers)
    assert session.get.call_args.kwargs["allow_redirects"] is False
    response.status = 429
    with pytest.raises(naver.NaverError, match="429"):
        await naver._get(session, "https://map.naver.com/")
    response.status = 200

    async def oversized(_size):
        yield b"x" * 5_000_001

    response.content.iter_chunked = oversized
    with pytest.raises(naver.NaverError, match="size limit"):
        await naver._get(session, "https://map.naver.com/")
    session.get.side_effect = asyncio.TimeoutError
    with pytest.raises(naver.NaverError, match="TimeoutError"):
        await naver._get(session, "https://map.naver.com/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (401, "access_denied"),
        (403, "access_denied"),
        (429, "rate_limited"),
        (503, "http_error"),
        (302, "http_error"),
    ],
)
async def test_status_classification_without_redirect_or_retry(status, code):
    response = MagicMock(status=status)
    response.json = AsyncMock()
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    with pytest.raises(naver.NaverError) as raised:
        await naver._get(session, "https://pcmap.place.naver.com/pet/18199503/home")
    assert raised.value.code == code
    session.get.assert_called_once()
    response.json.assert_not_called()


@pytest.mark.parametrize(
    "html,code",
    [
        ("서비스 이용이 제한되었습니다", "access_restricted"),
        ("과도한 접근 요청", "access_restricted"),
        ("<html>new layout</html>", "page_changed"),
        ("window.__APOLLO_STATE__ = invalid", "invalid_hours"),
    ],
)
def test_document_error_classification(html, code):
    with pytest.raises(naver.NaverError) as raised:
        naver.parse_hours(html, "18199503", STAMP)
    assert raised.value.code == code


@pytest.mark.parametrize(
    "next_day,expected", [(True, [0, 1440]), (False, None), (None, None)]
)
def test_explicit_24_hour_operation(next_day, expected):
    result = naver.parse_hours(
        page(
            [
                {
                    "day": "월",
                    "businessHours": {"start": "00:00", "end": "00:00"},
                    "showEndsNextDay": next_day,
                }
            ]
        ),
        "18199503",
        STAMP,
    )
    day = result["schedule"]["2026-09-21"]
    assert (day["open"] if day else None) == expected


@pytest.mark.asyncio
async def test_real_transport_to_parser_and_recovery():
    """One summary plus one HTML request; never replay token requests on failure."""
    summary = {
        "data": {
            "placeDetail": {
                "id": "18199503",
                "businessType": "pet",
                "name": "라온동물병원",
            }
        }
    }
    document = page(
        [
            {
                "day": "월",
                "businessHours": {"start": "10:00", "end": "19:00"},
                "breakHours": [{"start": "12:30", "end": "13:30"}],
            }
        ],
        [{"startDate": "09/24", "endDate": "09/26", "name": "추석 연휴"}],
    )
    summary_response = MagicMock(status=200)
    summary_response.json = AsyncMock(return_value=summary)
    page_response = MagicMock(status=200)
    session = MagicMock()
    bodies = ["서비스 이용이 제한되었습니다", document]

    for body in bodies:

        async def chunks(_size, content=body):
            yield content.encode("utf-8")

        page_response.content.iter_chunked = chunks
        responses = []
        for response in (summary_response, page_response):
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=response)
            responses.append(context)
        session.get.side_effect = responses
        result = await naver.async_place(session, "18199503", STAMP)
        if body == document:
            assert "hours_error" not in result
            assert today_hours({"_naver": result}, STAMP)["breaks"] == ["12:30 ~ 13:30"]
            assert result["schedule"]["2026-09-25"]["open"] is None
        else:
            assert result["hours_error_code"] == "access_restricted"
            assert "schedule" not in result
    assert session.get.call_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [{"schedule": {}}, {"hours_error": "restricted"}, naver.NaverError("failed")],
)
async def test_coordinator_enrichment(animal_hass, entry_data, record, outcome):
    from custom_components.korea_incubator.animal_medical.coordinator import (
        AnimalMedicalCoordinator,
    )

    coord = AnimalMedicalCoordinator(
        animal_hass, {**entry_data, "naver_place_url": "18199503"}
    )
    with (
        patch.object(coord, "_find", new_callable=AsyncMock, return_value=record),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.async_get_clientsession"
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.async_naver_place",
            new_callable=AsyncMock,
        ) as fetch,
    ):
        if isinstance(outcome, Exception):
            fetch.side_effect = outcome
        else:
            fetch.return_value = outcome
        result = await coord._async_update_data()
        assert (
            (result.get("_naver_error") == "failed")
            if isinstance(outcome, Exception)
            else result["_naver"] == outcome
        )


def test_malformed_groups_and_ranges():
    assert effective_schedule({"_naver": {"schedule": []}}) == {}
    bad = page([]).replace('"newBusinessHours": [', '"newBusinessHours": [null,')
    with pytest.raises(naver.NaverError):
        naver.parse_hours(bad, "18199503", STAMP)
    for start, end in [("bad", "09/22"), ("09/22", "bad"), ("09/01", "09/02")]:
        assert (
            naver.parse_hours(
                page([], [{"startDate": start, "endDate": end}]), "18199503", STAMP
            )["schedule"]
            == {}
        )
    with pytest.raises(ValueError):
        naver.place_id("https://map.naver.com/wrong/1")


@pytest.mark.asyncio
async def test_bad_summary_and_search():
    summary = {"data": {"placeDetail": {"id": "different"}}}
    with patch.object(naver, "_get", new_callable=AsyncMock) as get:
        get.return_value = summary
        with pytest.raises(naver.NaverError):
            await naver.async_place(MagicMock(), "18199503", STAMP)
        summary["data"]["placeDetail"] = {"id": "18199503", "businessType": "invalid"}
        with pytest.raises(naver.NaverError):
            await naver.async_place(MagicMock(), "18199503", STAMP)
        get.return_value = {
            "place": [{"id": "18199503", "title": "라온", "roadAddress": "서울"}]
        }
        assert await naver.async_search(MagicMock(), "라온") == [
            {"id": "18199503", "name": "라온", "address": "서울"}
        ]
        get.return_value = {"place": {}}
        with pytest.raises(naver.NaverError):
            await naver.async_search(MagicMock(), "라온")


@pytest.mark.asyncio
async def test_options_search_select_and_reload(animal_hass, entry_data):
    from custom_components.korea_incubator.config_flow import KoreaOptionsFlow

    entry = MagicMock(
        data=entry_data,
        options={
            "scan_interval_minutes": 60,
            "naver_place_url": "https://map.naver.com/p/entry/place/18199503",
        },
        entry_id="entry",
    )
    flow = KoreaOptionsFlow(entry)
    flow.hass = animal_hass
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.naver_options.async_search",
            new_callable=AsyncMock,
        ) as search,
        patch(
            "custom_components.korea_incubator.animal_medical.naver_options.async_get_clientsession"
        ),
    ):
        search.return_value = [{"id": "18199503", "name": "라온", "address": "서울"}]
        result = await flow.async_step_animal_medical_options(
            {"scan_interval_minutes": 60, "naver_query": "라온"}
        )
        assert result["step_id"] == "medical_naver"
        result = await flow.async_step_medical_naver(
            {"query": "라온", "selection": "18199503"}
        )
        assert result["data"]["naver_place_url"].endswith("18199503")
        animal_hass.config_entries.async_schedule_reload.assert_called_once_with(
            "entry"
        )
        entry.options = {}
        result = await flow.async_step_medical_naver(
            {"query": "라온", "selection": "18199503"}
        )
        assert result["data"]["naver_place_url"].endswith("18199503")
        result = await flow.async_step_medical_naver(
            {"query": "다른 검색", "selection": "18199503"}
        )
        assert result["step_id"] == "medical_naver"
        search.side_effect = naver.NaverError("HTTP 429")
        result = await flow.async_step_medical_naver()
        assert result["description_placeholders"]["error"] == "HTTP 429"


def page(rows, closures=None):
    return (
        "window.__APOLLO_STATE__ = "
        + json.dumps(
            {
                "ROOT_QUERY": {
                    "placeDetail(input)": {
                        "base": {"__ref": "PlaceDetailBase:18199503"},
                        "newBusinessHours": [
                            {
                                "businessHours": rows,
                                "comingIrregularClosedDays": closures or [],
                            }
                        ],
                    }
                }
            }
        )
        + ";"
    )


def test_observed_hours_and_special_holiday():
    html = page(
        [
            {
                "day": "월",
                "businessHours": {"start": "10:00", "end": "19:00"},
                "breakHours": [{"start": "12:30", "end": "13:30"}],
            },
            {"day": "일", "description": "정기휴무 (매주 일요일)"},
            {"day": "목(9/24)", "description": "추석 연휴 휴무"},
        ],
        [{"startDate": "09/24", "endDate": "09/26", "name": "추석 연휴"}],
    )
    result = naver.parse_hours(html, "18199503", STAMP)
    assert result["schedule"]["2026-09-21"] == {
        "open": [600, 1140],
        "breaks": [[750, 810]],
    }
    assert result["schedule"]["2026-09-27"]["open"] is None
    for day in (24, 25, 26):
        assert result["schedule"][f"2026-09-{day}"]["closure_reason"] == "추석 연휴"
    record = {
        "_kakao": {"schedule": {"2026-09-24": {"open": [600, 840], "breaks": []}}},
        "_naver": result,
    }
    assert effective_schedule(record)["2026-09-24"]["open"] is None
    assert today_hours(record, STAMP) == {
        "text": "10:00 ~ 19:00",
        "opening": "10:00",
        "closing": "19:00",
        "breaks": ["12:30 ~ 13:30"],
    }
    result["hours_error"] = "Naver HTTP 429"
    assert effective_schedule(record) == {}


def test_holiday_range_already_started_and_year_rollover():
    result = naver.parse_hours(
        page([], [{"startDate": "09/20", "endDate": "09/23", "name": "임시휴무"}]),
        "18199503",
        STAMP,
    )
    assert "2026-09-22" in result["schedule"]
    result = naver.parse_hours(
        page([], [{"startDate": "12/31", "endDate": "01/02"}]),
        "18199503",
        datetime(2026, 12, 31, tzinfo=SEOUL),
    )
    assert "2027-01-02" in result["schedule"]


@pytest.mark.parametrize(
    "html",
    [
        "접근 제한",
        "window.__APOLLO_STATE__ = broken;",
        'window.__APOLLO_STATE__ = {"ROOT_QUERY": {}}',
        page([{}]),
    ],
)
def test_restricted_or_malformed_page(html):
    with pytest.raises(naver.NaverError):
        naver.parse_hours(html, "18199503", STAMP)


@pytest.mark.parametrize(
    "url",
    [
        "18199503",
        "https://map.naver.com/p/entry/place/18199503?c=15",
        "https://pcmap.place.naver.com/pet/18199503/home",
    ],
)
def test_place_id(url):
    assert naver.place_id(url) == "18199503"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/18199503",
        "https://map.naver.com.evil.test/p/entry/place/18199503",
        "https://user@map.naver.com/p/entry/place/1",
        "http://map.naver.com/p/entry/place/1",
        "https://map.naver.com:123/p/entry/place/1",
        "bad",
    ],
)
def test_invalid_id(url):
    with pytest.raises(ValueError):
        naver.place_id(url)


def test_real_image_host_fix():
    url = "https://postfiles.pstatic.net/clinic/image.png?type=w580"
    assert photo_url(url) == url
    assert public_media({"summary": {"main_photo_url": url}}, "1")["main_photo"] == url
    assert photo_url("https://postfiles.pstatic.net.evil.test/image.png") is None


def test_entity_display_and_picture_fallback():
    record = {
        "_kakao": {
            "schedule": {"2026-09-21": {"open": [600, 1140], "breaks": [[750, 810]]}},
            "media": {"main_photo": "bad"},
            "summary": {"main_photo_url": "https://postfiles.pstatic.net/a.png"},
        },
        "_naver": {
            "coordinate": {"latitude": 37.5, "longitude": 127},
            "place_url": "https://map.naver.com/p/entry/place/18199503",
        },
    }
    primary = MagicMock(
        coordinator=MagicMock(data=record),
        extra_state_attributes={"api_record": {}},
        _entry_data={"kakao_place_id": "11558466"},
    )
    with patch(
        "custom_components.korea_incubator.animal_medical.compact_sensor.dt_util.now",
        return_value=STAMP,
    ):
        for kind, expected in {
            "hours": "10:00 ~ 19:00",
            "opening": "10:00",
            "closing": "19:00",
            "breaks": "12:30 ~ 13:30",
        }.items():
            assert MedicalInfoSensor(primary, kind).native_value == expected
        assert (
            MedicalInfoSensor(primary, "name").entity_picture
            == "https://postfiles.pstatic.net/a.png"
        )
        location = MedicalInfoSensor(primary, "location")
        assert location.native_value == "37.5, 127.0"
        assert location.extra_state_attributes["kakao_map_url"].endswith("11558466")
        assert location.extra_state_attributes["naver_map_url"].endswith("18199503")
        record["_kakao"]["schedule"]["2026-09-21"] = {"open": None, "breaks": []}
        assert MedicalInfoSensor(primary, "hours").native_value == "휴무"
        assert MedicalInfoSensor(primary, "breaks").native_value == "없음"


@pytest.mark.asyncio
async def test_fetch_optional_hours_failure_and_success():
    summary = {
        "data": {
            "placeDetail": {
                "id": "18199503",
                "name": "라온동물병원",
                "businessType": "pet",
                "images": {
                    "images": [{"originalUrl": "https://ldb-phinf.pstatic.net/a.jpg"}]
                },
            }
        }
    }
    with patch.object(naver, "_get", new_callable=AsyncMock) as get:
        get.side_effect = [summary, naver.NaverError("Naver HTTP 429")]
        result = await naver.async_place(MagicMock(), "18199503", STAMP)
        assert result["hours_error"] == "Naver HTTP 429"
        assert result["main_photo"] == "https://ldb-phinf.pstatic.net/a.jpg"
        get.side_effect = [summary, page([])]
        assert (await naver.async_place(MagicMock(), "18199503", STAMP))[
            "schedule"
        ] == {}
        get.side_effect = [{}]
        with pytest.raises(naver.NaverError):
            await naver.async_place(MagicMock(), "18199503", STAMP)
