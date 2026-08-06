import ssl
from logging import getLogger

import pytz
from homeassistant.const import Platform

DOMAIN = "korea_incubator"
LOGGER = getLogger(__package__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.CALENDAR,
    Platform.WEATHER,
]

CURRENCY_KRW = "KRW"
ENERGY_KILO_WATT_HOUR = "kWh"
TZ_ASIA_SEOUL = pytz.timezone("Asia/Seoul")
SSL_CONTEXT = ssl.create_default_context()

CONF_ENTRY_TYPE = "service"  # 기존 service 필드와 호환을 위해 service 사용하거나 별도 정의

ENTRY_WEATHER = "weather_warning"
ENTRY_TRANSIT = "transit"
ENTRY_FUEL = "fuel"
ENTRY_SCHOOL = "school"
ENTRY_DISASTER = "disaster"
ENTRY_SAFETY_ALERT = "safety_alert"
ENTRY_KEPCO = "kepco"
ENTRY_GASAPP = "gasapp"
ENTRY_ARISU = "arisu"
ENTRY_PHARMACY = "pharmacy"
ENTRY_AIRKOREA = "airkorea"
ENTRY_KMA_WEATHER = "kma_weather"
ENTRY_EARTHQUAKE = "earthquake"
ENTRY_GOODSFLOW = "goodsflow"
ENTRY_KAKAOMAP = "kakaomap"
ENTRY_CJ_ONE_DELIVERY = "cj_one_delivery"
