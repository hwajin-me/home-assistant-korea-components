import ssl
from logging import getLogger

DOMAIN = "korea_incubator"
LOGGER = getLogger(__package__)

CURRENCY_KRW = "KRW"
ENERGY_KILO_WATT_HOUR = "kWh"

SSL_CONTEXT = ssl.create_default_context()
