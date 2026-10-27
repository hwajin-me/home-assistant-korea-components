"""One upstream outage produces one coordinator log and can recover."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import curl_cffi
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.korea_incubator.const import LOGGER
from custom_components.korea_incubator.safety_alert.device import SafetyAlertDevice


@pytest.mark.parametrize(
    "failure",
    [
        curl_cffi.CurlError("Connection timed out after 15001 milliseconds", 28),
        TimeoutError("timeout"),
    ],
)
async def test_outage_logs_once_preserves_data_and_recovers(tmp_path, caplog, failure):
    hass = HomeAssistant(str(tmp_path))
    device = SafetyAlertDevice(hass, "entry", "1100000000", "서울특별시")
    response = MagicMock(
        status_code=200,
        text='<div class="board-count"><span>1</span></div>'
        '<div class="board-listarea"><table><tbody>'
        "<tr><td>호우</td><td><a>안전한 장소로 이동하세요</a></td></tr>"
        "</tbody></table></div>",
    )
    session = MagicMock(get=AsyncMock(return_value=response))
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)

    async def update():
        await device.async_update()
        return device.data

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=device.unique_id,
        config_entry=None,
        update_method=update,
    )
    caplog.set_level(logging.DEBUG, logger=LOGGER.name)
    try:
        with patch(
            "custom_components.korea_incubator.safety_alert.api.curl_cffi.AsyncSession",
            return_value=context,
        ):
            await coordinator.async_refresh()
            assert coordinator.last_update_success
            previous = device.data
            last_success = device._last_update_success
            session.get.side_effect = failure
            caplog.clear()
            await coordinator.async_refresh()
            await coordinator.async_refresh()
            assert not coordinator.last_update_success
            assert not device.available
            assert device.data is previous
            assert device._last_update_success == last_success
            assert coordinator.data is previous
            assert coordinator.last_exception.__cause__.__cause__ is failure
            errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
            assert len(errors) == 1
            assert "Error fetching safety_alert_1100000000 data" in errors[0].message

            # A recovered request with genuinely no alerts may clear old data.
            session.get.side_effect = None
            response.text = (
                '<div class="board-count"><span>0</span></div>'
                '<div class="board-listarea"><table><tbody></tbody></table></div>'
            )
            await coordinator.async_refresh()
            assert coordinator.last_update_success
            assert device.available
            assert device.data["metadata"]["count"] == 0
            assert device.data["parsed_data"]["data"] == []
    finally:
        await hass.async_stop()
