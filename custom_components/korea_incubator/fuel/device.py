from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from ..const import DOMAIN
from . import SIDO_CODES, FUEL_TYPES

def fuel_device(sido_code: str, fuel_code: str) -> DeviceInfo:
    area = SIDO_CODES.get(sido_code, sido_code)
    fuel = FUEL_TYPES.get(fuel_code, fuel_code)
    return DeviceInfo(identifiers={(DOMAIN, f"fuel_{sido_code}_{fuel_code}")},
                      name=f"유가정보 - {area} {fuel}",
                      manufacturer="한국석유공사", model="Opinet",
                      entry_type=DeviceEntryType.SERVICE)
