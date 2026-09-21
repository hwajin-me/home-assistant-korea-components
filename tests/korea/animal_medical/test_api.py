"""Contract, transport and identity tests for both official list endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

pytestmark = pytest.mark.asyncio

from custom_components.korea_incubator.animal_medical.api import (
    AnimalMedicalApiError,
    AnimalMedicalAuthError,
    async_fetch_institutions,
    find_selected_institution,
)

RECORD = {"MNG_NO": "A1", "OPN_ATMY_GRP_CD": "3000000"}


def payload(items=None, total=1, code="00"):
    return {
        "response": {
            "header": {"resultCode": code},
            "body": {"items": items, "totalCount": total},
        }
    }


def session_for(body, status=200):
    response = MagicMock(status=status)
    response.text = AsyncMock(
        return_value=body if isinstance(body, str) else json.dumps(body)
    )
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    return session, response


@pytest.mark.parametrize(
    "kind,endpoint",
    [
        ("hospital", "animal_hospitals"),
        ("pharmacy", "animal_pharmacies"),
    ],
)
@pytest.mark.parametrize("key", [" a+b/c= ", "a%2Bb%2Fc%3D"])
async def test_endpoint_filters_and_key_encoding(kind, endpoint, key):
    session, _ = session_for(payload({"item": RECORD}))
    assert await async_fetch_institutions(
        session,
        key,
        kind,
        page=3,
        rows=999,
        road_address=" 서울 ",
        municipality_code=" 3000000 ",
        business_name=" 병원 ",
    ) == ([RECORD], 1)
    assert (
        session.get.call_args.args[0]
        == f"https://apis.data.go.kr/1741000/{endpoint}/info"
    )
    assert session.get.call_args.kwargs["params"] == {
        "serviceKey": "a+b/c=",
        "pageNo": "3",
        "numOfRows": "100",
        "returnType": "json",
        "cond[ROAD_NM_ADDR::LIKE]": "서울",
        "cond[OPN_ATMY_GRP_CD::EQ]": "3000000",
        "cond[BPLC_NM::LIKE]": "병원",
    }


async def test_minimum_page_and_rows_omit_blank_filters():
    session, _ = session_for(payload(total=0))
    assert await async_fetch_institutions(
        session, "key", "hospital", page=-1, rows=0, road_address=" "
    ) == ([], 0)
    assert session.get.call_args.kwargs["params"] == {
        "serviceKey": "key",
        "pageNo": "1",
        "numOfRows": "1",
        "returnType": "json",
    }


@pytest.mark.parametrize(
    "items,expected",
    [
        (None, []),
        ("", []),
        ({}, []),
        ({"item": None}, []),
        ({"item": ""}, []),
        ({"item": []}, []),
        ({"item": RECORD}, [RECORD]),
        ({"item": [RECORD]}, [RECORD]),
    ],
)
@pytest.mark.parametrize("code", ["00", "0", 0])
async def test_valid_response_shapes(items, expected, code):
    session, _ = session_for(payload(items, total=str(len(expected)), code=code))
    assert await async_fetch_institutions(session, "key", "hospital") == (
        expected,
        len(expected),
    )


@pytest.mark.parametrize(
    "body",
    [
        "",
        "not-json",
        "null",
        "[]",
        "{}",
        '{"response": null}',
        {"response": {"header": {}, "body": {}}},
        payload(total=-1),
        payload(total=True),
        payload(total="NaN"),
        payload(total=1.5),
        payload(items=[]),
        payload(items={"item": 42}),
        payload(items={"item": [None]}),
        payload(items={"item": RECORD}, total=0),
        {"response": {"header": {"resultCode": "00"}, "body": []}},
    ],
)
async def test_invalid_shapes_are_errors_not_empty_success(body):
    session, _ = session_for(body)
    with pytest.raises(AnimalMedicalApiError, match="Invalid API JSON"):
        await async_fetch_institutions(session, "key", "hospital")


@pytest.mark.parametrize(
    "code,error",
    [
        ("20", AnimalMedicalAuthError),
        ("30", AnimalMedicalAuthError),
        ("31", AnimalMedicalAuthError),
        ("-4", AnimalMedicalAuthError),
        ("22", AnimalMedicalApiError),
        ("-1", AnimalMedicalApiError),
    ],
)
@pytest.mark.parametrize("xml", [False, True])
async def test_api_errors_in_json_and_gateway_xml(code, error, xml):
    body = (
        (
            f"<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>{code}</returnReasonCode>"
            "</cmmMsgHeader></OpenAPI_ServiceResponse>"
        )
        if xml
        else payload(code=code)
    )
    session, _ = session_for(body)
    with pytest.raises(error):
        await async_fetch_institutions(session, "key", "hospital")


@pytest.mark.parametrize(
    "body",
    [
        "<broken",
        "<html>gateway failed</html>",
        "<response><header><resultCode>00</resultCode></header></response>",
    ],
)
async def test_other_xml_is_not_accepted_as_empty_success(body):
    session, _ = session_for(body)
    with pytest.raises(AnimalMedicalApiError):
        await async_fetch_institutions(session, "key", "pharmacy")


async def test_xml_result_code_auth_error():
    session, _ = session_for(
        "<response><header><resultCode>30</resultCode></header></response>"
    )
    with pytest.raises(AnimalMedicalAuthError):
        await async_fetch_institutions(session, "key", "pharmacy")


@pytest.mark.parametrize("status", [401, 403])
async def test_http_auth(status):
    session, _ = session_for("", status=status)
    with pytest.raises(AnimalMedicalAuthError):
        await async_fetch_institutions(session, "key", "hospital")


@pytest.mark.parametrize(
    "exc",
    [
        aiohttp.ClientConnectionError("url?serviceKey=SECRET"),
        TimeoutError("SECRET"),
        UnicodeDecodeError("utf8", b"x", 0, 1, "SECRET"),
    ],
)
async def test_transport_errors_are_redacted(exc):
    session, response = session_for("")
    response.text.side_effect = exc
    with pytest.raises(AnimalMedicalApiError) as error:
        await async_fetch_institutions(session, "SECRET", "hospital")
    assert "SECRET" not in str(error.value)


async def test_http_failure_is_not_hidden_by_success_body():
    session, response = session_for(payload(total=0), status=500)
    response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        MagicMock(), (), status=500
    )
    with pytest.raises(AnimalMedicalApiError):
        await async_fetch_institutions(session, "key", "hospital")
    response.text.assert_awaited_once()


async def test_invalid_kind_does_not_request():
    session = MagicMock()
    with pytest.raises(AnimalMedicalApiError, match="Unknown"):
        await async_fetch_institutions(session, "key", "other")
    session.get.assert_not_called()


async def test_exact_identity_not_similar_name_or_other_municipality():
    records = [
        {"MNG_NO": "other", "OPN_ATMY_GRP_CD": "3000000"},
        {"MNG_NO": "A1", "OPN_ATMY_GRP_CD": "3010000"},
        RECORD,
    ]
    assert find_selected_institution(records, "A1", "3000000") is RECORD
    assert find_selected_institution(records, "absent", "3000000") is None


@pytest.mark.parametrize("key", ["a+b/c=", "a%2Bb%2Fc%3D"])
async def test_actual_aiohttp_query_encoding_and_shared_session(monkeypatch, key):
    """Verify URL encoding with a loopback HTTP server, not a mocked get()."""
    from custom_components.korea_incubator.animal_medical import ANIMAL_MEDICAL_TYPES

    async def handle(request):
        assert request.query["serviceKey"] == "a+b/c="
        assert request.query["cond[ROAD_NM_ADDR::LIKE]"] == "서울 종로구"
        return web.json_response(payload({"item": RECORD}))

    app = web.Application()
    app.router.add_get("/info", handle)
    async with TestServer(app) as server, aiohttp.ClientSession() as session:
        monkeypatch.setitem(
            ANIMAL_MEDICAL_TYPES,
            "hospital",
            {
                "name": "동물병원",
                "url": str(server.make_url("/info")),
            },
        )
        assert await async_fetch_institutions(
            session, key, "hospital", road_address="서울 종로구"
        ) == ([RECORD], 1)
        assert not session.closed


@pytest.mark.parametrize("key", ["", "secret%2Btoken"])
async def test_server_message_details_are_sanitized(key):
    session, _ = session_for(payload(code="22"))
    message = payload(code="22")
    message["response"]["header"]["resultMsg"] = (
        "Daily quota reached serviceKey=othersecret secret+token secret%2Btoken"
    )
    session, _ = session_for(message)
    with pytest.raises(AnimalMedicalApiError) as exc:
        await async_fetch_institutions(session, key, "hospital")
    assert "daily quota exceeded (22)" in str(exc.value)
    assert "Daily quota reached" in str(exc.value)
    assert "othersecret" not in str(exc.value)
    if key:
        assert "secret+token" not in str(exc.value)
        assert "secret%2Btoken" not in str(exc.value)


async def test_xml_server_error_message_preserved():
    session, _ = session_for(
        "<response><header><resultCode>30</resultCode>"
        "<resultMsg>Expired service key</resultMsg></header></response>"
    )
    with pytest.raises(AnimalMedicalAuthError, match="Expired service key"):
        await async_fetch_institutions(session, "token", "hospital")
