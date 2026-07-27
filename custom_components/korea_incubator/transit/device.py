"""Transit device helpers."""
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from ..const import DOMAIN
from . import SUBWAY_LINES


def subway_device(station, direction, line_id=""):
    ln = SUBWAY_LINES.get(line_id, "")
    label = f"지하철 - {station}역 {ln} {direction}".strip()
    did = f"subway_{station}_{direction}_{line_id}"
    return DeviceInfo(identifiers={(DOMAIN, did)}, name=label,
                      manufacturer="서울교통공사", model="실시간 도착정보",
                      entry_type=DeviceEntryType.SERVICE)


def bus_stop_device(stop_id, stop_name):
    """One device per bus stop."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"bus_{stop_id}")},
        name=f"버스 - {stop_name}",
        manufacturer="KakaoMap", model="버스 도착정보",
        entry_type=DeviceEntryType.SERVICE,
    )
