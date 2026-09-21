"""Selected pharmacy using shared persisted polling and Kakao date-specific hours."""

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..animal_medical.coordinator import AnimalMedicalCoordinator
from .api import fetch_complete_detail as fetch_detail


class PharmacyCoordinator(AnimalMedicalCoordinator):
    service_name = "pharmacy"
    record_name_key = "dutyName"

    def _matches_identity(self, record):
        return record.get("hpid") == self._entry_data["hpid"]

    async def _find(self, business_name):
        return await fetch_detail(
            async_get_clientsession(self.hass),
            self._entry_data["api_key"],
            self._entry_data["hpid"],
        )
