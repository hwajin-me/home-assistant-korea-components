"""Map ENTRY_* type to the list of llm.Tool factory callables it should expose."""
from __future__ import annotations

from typing import Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import (
    ENTRY_AIRKOREA,
    ENTRY_ARISU,
    ENTRY_DISASTER,
    ENTRY_EARTHQUAKE,
    ENTRY_FUEL,
    ENTRY_GASAPP,
    ENTRY_KEPCO,
    ENTRY_KMA_WEATHER,
    ENTRY_PHARMACY,
    ENTRY_SAFETY_ALERT,
    ENTRY_SCHOOL,
    ENTRY_TRANSIT,
    ENTRY_WEATHER,
)

ToolFactory = Callable[[HomeAssistant, str], llm.Tool]


def _factory(cls: type) -> ToolFactory:
    def make(hass: HomeAssistant, entry_id: str) -> llm.Tool:
        return cls(hass, entry_id)
    return make


def _build() -> dict[str, list[ToolFactory]]:
    from .airkorea_tool import GetAirQualityTool
    from .disaster_tool import GetDisasterMessagesTool
    from .earthquake_tool import GetRecentEarthquakesTool
    from .fuel_tool import GetFuelPricesTool
    from .kma_weather_tool import GetKMAWeatherForecastTool
    from .pharmacy_tool import GetOpenPharmaciesTool
    from .safety_alert_tool import GetSafetyAlertsTool
    from .school_tool import GetSchoolMealTool, GetSchoolTimetableTool
    from .transit_tool import GetBusArrivalsTool, GetSubwayArrivalsTool
    from .utility_tools import (
        GetElectricityUsageTool,
        GetGasBillTool,
        GetWaterBillTool,
    )
    from .weather_warning_tool import GetWeatherWarningsTool

    return {
        ENTRY_KMA_WEATHER: [_factory(GetKMAWeatherForecastTool)],
        ENTRY_WEATHER: [_factory(GetWeatherWarningsTool)],
        ENTRY_AIRKOREA: [_factory(GetAirQualityTool)],
        ENTRY_TRANSIT: [
            _factory(GetSubwayArrivalsTool),
            _factory(GetBusArrivalsTool),
        ],
        ENTRY_FUEL: [_factory(GetFuelPricesTool)],
        ENTRY_SCHOOL: [
            _factory(GetSchoolMealTool),
            _factory(GetSchoolTimetableTool),
        ],
        ENTRY_DISASTER: [_factory(GetDisasterMessagesTool)],
        ENTRY_SAFETY_ALERT: [_factory(GetSafetyAlertsTool)],
        ENTRY_KEPCO: [_factory(GetElectricityUsageTool)],
        ENTRY_GASAPP: [_factory(GetGasBillTool)],
        ENTRY_ARISU: [_factory(GetWaterBillTool)],
        ENTRY_PHARMACY: [_factory(GetOpenPharmaciesTool)],
        ENTRY_EARTHQUAKE: [_factory(GetRecentEarthquakesTool)],
    }


TOOLS_BY_ETYPE: dict[str, list[ToolFactory]] = _build()
