"""Human pharmacy regression tests using the shared medical flow fixtures."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.util import dt as dt_util

from custom_components.korea_incubator import async_remove_entry, async_setup_entry
from custom_components.korea_incubator.config_flow import KoreaOptionsFlow
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.pharmacy import api
from custom_components.korea_incubator.pharmacy.coordinator import PharmacyCoordinator
from custom_components.korea_incubator.pharmacy.migration import remove_legacy_count
from custom_components.korea_incubator.pharmacy.sensor import PharmacySensor

pytestmark = pytest.mark.asyncio
P = "custom_components.korea_incubator.pharmacy"
RECORD = {
    "hpid": "C1",
    "dutyName": "약국",
    "dutyAddr": "서울 종로구 사직로 1",
    "dutyTel1": "02-123-4567",
    "wgs84Lat": "37.5",
    "wgs84Lon": "127.0",
    "dutyTime1s": "0900",
    "dutyTime1c": "1800",
    "unknownFutureField": "preserved",
}
DATA = {
    "service": "pharmacy",
    "api_key": "key",
    "q0": "서울특별시",
    "q1": "종로구",
    "business_name": "약국",
    "hpid": "C1",
    "kakao_place_id": "123",
    "scan_interval_minutes": 30,
}


def http(xml, status=200):
    response = MagicMock(status=status)
    response.text = AsyncMock(return_value=xml)
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    return session


def xml(record=RECORD, total="1"):
    item = "".join(f"<{k}>{v}</{k}>" for k, v in record.items())
    return f"<response><header><resultCode>00</resultCode></header><body><items><item>{item}</item></items><totalCount>{total}</totalCount></body></response>"


async def test_api_list_detail_and_action():
    session = http(xml())
    records, total = await api.fetch_page(
        session, "a%2Bb", "서울", name="약국", page=0, num=200
    )
    assert (records, total) == ([RECORD], 1)
    params = session.get.call_args.kwargs["params"]
    assert params["serviceKey"] == "a+b"
    assert params["pageNo"] == "1" and params["numOfRows"] == "100"
    assert params["QN"] == "약국"
    assert await api.fetch_detail(session, "key", "C1") == RECORD
    assert session.get.call_args.kwargs["params"]["HPID"] == "C1"
    result = (await api.fetch_pharmacies(session, "key", "서울"))[0]
    assert result["duty_time"] == {"월": "0900~1800"}
    assert result["api_record"] == RECORD
    with pytest.raises(api.PharmacyApiError, match="missing or ambiguous"):
        await api.fetch_detail(session, "key", "wrong")


@pytest.mark.parametrize(
    "payload,status,kind",
    [
        ("", 401, api.PharmacyAuthError),
        ("", 403, api.PharmacyAuthError),
        ("", 500, api.PharmacyApiError),
        ("broken", 200, api.PharmacyApiError),
        ("<response/>", 200, api.PharmacyApiError),
        ("<response><resultCode>00</resultCode></response>", 200, api.PharmacyApiError),
        (xml(total="bad"), 200, api.PharmacyApiError),
        (xml(total="-1"), 200, api.PharmacyApiError),
        (
            "<response><returnReasonCode>30</returnReasonCode><returnAuthMsg>bad secret</returnAuthMsg></response>",
            200,
            api.PharmacyAuthError,
        ),
        (
            "<response><resultCode>22</resultCode><resultMsg>quota secret</resultMsg></response>",
            200,
            api.PharmacyApiError,
        ),
    ],
)
async def test_api_errors(payload, status, kind):
    with pytest.raises(kind) as err:
        await api.fetch_page(http(payload, status), "secret", "서울")
    assert "secret" not in str(err.value)


async def test_transport_and_empty_data():
    session = http("")
    session.get.side_effect = aiohttp.ClientError("url?serviceKey=secret")
    with pytest.raises(api.PharmacyApiError, match="ClientError") as err:
        await api.fetch_page(session, "secret", "서울")
    assert "secret" not in str(err.value)
    session = http(
        "<response><resultCode>0</resultCode><body><items/></body></response>"
    )
    assert await api.fetch_page(session, "", "서울") == ([], 0)


@pytest.fixture
def fetch():
    with (
        patch(
            f"{P}.config_flow.fetch_detail", new_callable=AsyncMock, return_value=RECORD
        ),
        patch(f"{P}.config_flow.fetch_page", new_callable=AsyncMock) as fetch,
        patch(f"{P}.config_flow.async_get_clientsession", return_value=MagicMock()),
    ):
        fetch.return_value = ([RECORD], 1)
        yield fetch


async def test_flow_selection_and_kakao(flow, fetch, kakao_network):
    form = await flow.async_step_pharmacy()
    search = form["data_schema"]({"api_key": " key "})
    assert search["scan_interval_minutes"] == 60
    assert (await flow.async_step_pharmacy(search))["step_id"] == "pharmacy_select"
    kakao_network[0].return_value = (
        [
            {
                "id": "123",
                "name": "약국",
                "address": RECORD["dutyAddr"],
                "phone": RECORD["dutyTel1"],
            }
        ],
        1,
    )
    result = await flow.async_step_pharmacy_select({"selection": "C1"})
    assert result["type"] == "create_entry"
    assert result["data"]["service"] == "pharmacy"
    assert result["data"]["hpid"] == "C1"
    assert result["data"]["kakao_place_id"] == "123"
    assert flow.unique_id == "pharmacy_C1"


@pytest.mark.parametrize(
    "error,code",
    [
        (api.PharmacyAuthError("bad key"), "animal_invalid_auth"),
        (api.PharmacyApiError("missing HPID"), "animal_cannot_connect"),
    ],
)
async def test_selection_validates_detail_endpoint(flow, fetch, error, code):
    await flow.async_step_pharmacy(DATA)
    with patch(
        f"{P}.config_flow.fetch_detail", new_callable=AsyncMock, side_effect=error
    ):
        result = await flow.async_step_pharmacy_select({"selection": "C1"})
    assert result["errors"]["base"] == code
    assert result["step_id"] == "pharmacy_select"


async def test_flow_pages_errors_and_research(flow, fetch):
    fetch.return_value = ([RECORD], 101)
    await flow.async_step_pharmacy({**DATA, "road_address": "다른주소"})
    result = await flow.async_step_pharmacy_select()
    assert result["description_placeholders"]["pages"] == "2"
    assert (await flow.async_step_pharmacy_select({"selection": "bad"}))["errors"]
    result = await flow.async_step_pharmacy_select({"selection": "__next__"})
    assert result["errors"]["base"] == "animal_cannot_connect"  # repeated page
    fetch.return_value = ([{**RECORD, "hpid": "C2"}], 101)
    assert (await flow.async_step_pharmacy_select({"selection": "__next__"}))[
        "description_placeholders"
    ]["page"] == "2"
    fetch.return_value = ([RECORD], 101)
    await flow.async_step_pharmacy_select({"selection": "__previous__"})
    assert flow._pharmacy_page == 1
    assert (await flow.async_step_pharmacy_select({"selection": "__search__"}))[
        "step_id"
    ] == "pharmacy"
    fetch.side_effect = api.PharmacyAuthError("key rejected")
    assert (await flow.async_step_pharmacy(DATA))["errors"][
        "base"
    ] == "animal_invalid_auth"


@pytest.mark.parametrize("old_hpid", [None, "C1"])
async def test_reconfigure_legacy_and_duplicate(flow, fetch, kakao_network, old_hpid):
    entry = MagicMock(
        entry_id="entry",
        data={"service": "pharmacy", "api_key": "key", "q0": "서울"},
        unique_id=None,
    )
    flow.context = {"source": "reconfigure"}
    entry.data["hpid"] = old_hpid
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    assert (await flow.async_step_reconfigure())["step_id"] == "pharmacy"
    await flow.async_step_pharmacy(DATA)
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = MagicMock(
        entry_id="other"
    )
    assert (await flow.async_step_pharmacy_select({"selection": "C1"}))[
        "reason"
    ] == "already_configured"
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = entry
    flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
    await flow.async_step_pharmacy_select({"selection": "C1"})
    await flow.async_step_animal_kakao({"selection": "123"})
    assert (
        flow.async_update_reload_and_abort.call_args.kwargs["unique_id"]
        == "pharmacy_C1"
    )


async def test_reauth_and_options(flow, fetch):
    entry = MagicMock(data=DATA, options={})
    flow._get_reauth_entry = MagicMock(return_value=entry)
    assert (await flow.async_step_reauth(DATA))["step_id"] == "pharmacy_reauth"
    with patch(f"{P}.config_flow.fetch_detail", new_callable=AsyncMock) as detail:
        for error, expected in [
            (api.PharmacyAuthError("bad"), "animal_invalid_auth"),
            (api.PharmacyApiError("quota"), "animal_cannot_connect"),
        ]:
            detail.side_effect = error
            assert (await flow.async_step_pharmacy_reauth({"api_key": "new"}))[
                "errors"
            ]["base"] == expected
        detail.side_effect = None
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
        await flow.async_step_pharmacy_reauth({"api_key": " new "})
        assert flow.async_update_reload_and_abort.call_args.kwargs["data_updates"] == {
            "api_key": "new"
        }
    options = KoreaOptionsFlow(entry)
    options.hass = flow.hass
    assert (await options.async_step_init())["step_id"] == "animal_medical_options"


async def test_coordinator_cache_identity_and_details(animal_hass, memory_store):
    entry = MagicMock(entry_id="pharmacy", options={}, pref_disable_polling=False)
    c = PharmacyCoordinator(animal_hass, DATA, config_entry=entry)
    with (
        patch(
            f"{P}.coordinator.fetch_detail", new_callable=AsyncMock, return_value=RECORD
        ) as detail,
        patch(f"{P}.coordinator.async_get_clientsession", return_value=MagicMock()),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        result = await c._async_update_data()
        assert result["hpid"] == "C1"
        assert detail.call_args.args[2] == "C1"
    saved = memory_store.async_save.call_args.args[0]
    memory_store.async_load.return_value = saved
    restored = PharmacyCoordinator(animal_hass, DATA, config_entry=entry)
    await restored.async_restore()
    restored._find = AsyncMock()
    assert (await restored._async_update_data())["hpid"] == "C1"
    restored._find.assert_not_awaited()
    assert restored.next_refresh == restored.last_refresh + timedelta(minutes=30)
    saved["record"]["hpid"] = "other"
    invalid = PharmacyCoordinator(animal_hass, DATA, config_entry=entry)
    await invalid.async_restore()
    assert invalid._restored_data is None
    invalid._find = AsyncMock(side_effect=api.PharmacyAuthError("bad"))
    with pytest.raises(ConfigEntryAuthFailed):
        await invalid._async_update_data()


async def test_sensor_details_gps_and_unknown():
    c = MagicMock(
        data=RECORD,
        last_refresh=dt_util.utcnow(),
        next_refresh=dt_util.utcnow(),
        interval_minutes=30,
    )
    sensor = PharmacySensor(c, DATA)
    assert sensor.unique_id == f"{DOMAIN}_pharmacy_C1"
    assert sensor.native_value is None
    attrs = sensor.extra_state_attributes
    assert attrs["latitude"] == 37.5 and attrs["longitude"] == 127
    assert attrs["api_record"]["unknownFutureField"] == "preserved"
    assert attrs["opening_hours_source"] == "kakao"
    c.data = {**RECORD, "dutyEtc": "휴게시간 13:00~14:00"}
    assert sensor.extra_state_attributes["public_notes"] == "휴게시간 13:00~14:00"
    assert attrs["weekly_hours"]["mon"] == {"start": "0900", "end": "1800"}
    c.data = {"_kakao": {"summary": {"point": {"lat": 37.6, "lon": 127.1}}}}
    assert sensor.extra_state_attributes["latitude"] == 37.6
    c.data = None
    c.last_refresh = c.next_refresh = None
    assert not sensor.extra_state_attributes["location_available"]


async def test_legacy_setup_requires_selection(animal_hass):
    with pytest.raises(ConfigEntryError):
        await async_setup_entry(
            animal_hass, MagicMock(data={"service": "pharmacy", "api_key": "key"})
        )


async def test_setup_reload_and_remove(animal_hass):
    entry = MagicMock(data=DATA, entry_id="entry")
    coordinator = MagicMock(
        async_config_entry_first_refresh=AsyncMock(), async_restore=AsyncMock()
    )
    with (
        patch(f"{P}.coordinator.PharmacyCoordinator", return_value=coordinator),
        patch(f"{P}.migration.remove_legacy_count"),
        patch(f"{P}.services.async_register_pharmacy_service"),
        patch(
            "custom_components.korea_incubator.async_setup_llm_api",
            new_callable=AsyncMock,
        ),
    ):
        animal_hass.is_running = False
        assert await async_setup_entry(animal_hass, entry)
        coordinator.async_restore.assert_awaited_once()
        assert await async_setup_entry(animal_hass, entry)
        assert coordinator.async_restore.await_count == 1
        assert coordinator.async_config_entry_first_refresh.await_count == 2
    with patch("homeassistant.helpers.storage.Store") as store:
        store.return_value.async_remove = AsyncMock()
        await async_remove_entry(animal_hass, entry)
        assert store.call_args.args[2] == f"{DOMAIN}.pharmacy.entry"


async def test_legacy_registry_scoping(animal_hass):
    entry = MagicMock(data=DATA, entry_id="entry")
    with (
        patch(f"{P}.migration.er.async_get") as registry,
        patch(f"{P}.migration.er.async_entries_for_config_entry") as entities,
    ):
        entities.return_value = [
            MagicMock(
                platform=DOMAIN,
                unique_id=f"{DOMAIN}_pharmacy_서울특별시_종로구",
                entity_id="sensor.old",
            ),
            MagicMock(platform=DOMAIN, unique_id="keep", entity_id="sensor.keep"),
        ]
        remove_legacy_count(animal_hass, entry)
        registry.return_value.async_remove.assert_called_once_with("sensor.old")


async def test_empty_key_error_redaction_branch():
    with pytest.raises(api.PharmacyApiError):
        await api.fetch_page(http("<response/>"), "", "서울")


async def test_service_reload_key_and_count_validation(animal_hass):
    animal_hass.services = MagicMock()
    import voluptuous as vol

    from custom_components.korea_incubator.pharmacy.services import (
        async_register_pharmacy_service,
    )

    async_register_pharmacy_service(animal_hass, "")
    animal_hass.services.async_register.assert_not_called()
    async_register_pharmacy_service(animal_hass, "old")
    async_register_pharmacy_service(animal_hass, "new")
    registration = animal_hass.services.async_register.call_args
    schema = registration.kwargs["schema"]
    with pytest.raises(vol.Invalid):
        schema({"region": "서울", "count": 101})
    callback = registration.args[2]
    with (
        patch(f"{P}.services.async_get_clientsession", return_value=MagicMock()),
        patch(
            f"{P}.services.fetch_pharmacies",
            new_callable=AsyncMock,
            return_value=[RECORD],
        ) as fetch,
    ):
        result = await callback(MagicMock(data={"region": "서울"}))
    assert result == {"pharmacies": [RECORD], "count": 1}
    assert fetch.call_args.args[1] == "new"


@pytest.mark.parametrize(
    "state,only_open,expected",
    [
        (None, False, 1),
        (None, True, 0),
        ("open", True, 1),
        ("closed", False, 1),
        ("break", True, 0),
    ],
)
async def test_llm_uses_same_selected_pharmacy_state(
    animal_hass, state, only_open, expected
):
    from custom_components.korea_incubator.llm_api.pharmacy_tool import (
        GetOpenPharmaciesTool,
    )

    animal_hass.data[DOMAIN] = {
        "entry": {"coordinator": MagicMock(data=RECORD, last_update_success=True)}
    }
    tool = GetOpenPharmaciesTool(animal_hass, "entry")
    with patch(
        "custom_components.korea_incubator.llm_api.pharmacy_tool.current_state",
        return_value=state,
    ):
        result = await tool.async_call(
            animal_hass, MagicMock(tool_args={"only_open": only_open}), None
        )
    assert result["count"] == expected
    if expected:
        assert result["pharmacies"][0]["status"] == state
        assert result["pharmacies"][0]["hpid"] == "C1"


async def test_llm_missing_or_failed_data(animal_hass):
    from custom_components.korea_incubator.llm_api.pharmacy_tool import (
        GetOpenPharmaciesTool,
    )

    tool = GetOpenPharmaciesTool(animal_hass, "entry")
    assert "error" in await tool.async_call(animal_hass, MagicMock(), None)
    animal_hass.data[DOMAIN] = {
        "entry": {"coordinator": MagicMock(data=RECORD, last_update_success=False)}
    }
    assert "error" in await tool.async_call(animal_hass, MagicMock(), None)
