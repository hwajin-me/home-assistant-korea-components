from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from ..const import DOMAIN

def school_device(entry) -> DeviceInfo:
    """Device per school. Name = school name."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"school_{entry.data['region_code']}_{entry.data['school_code']}")},
        name=entry.data.get("school_name", "학교"),
        manufacturer="NEIS",
        model="학교정보",
        entry_type=dr.DeviceEntryType.SERVICE,
    )
