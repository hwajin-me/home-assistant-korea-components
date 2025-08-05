import ssl
from logging import getLogger

from homeassistant.const import Platform

DOMAIN = "korea_incubator"
LOGGER = getLogger(__package__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR
]

CURRENCY_KRW = "KRW"
ENERGY_KILO_WATT_HOUR = "kWh"

SSL_CONTEXT = ssl.create_default_context()
