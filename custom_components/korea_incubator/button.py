"""Button entities for Donghaeng Lottery purchases."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .lottery import LotteryCoordinator, LotteryError


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create purchase controls for a Donghaeng Lottery entry."""
    if entry.data.get("service") != "dh_lottery":
        return
    coordinator: LotteryCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            PensionAutoPurchaseButton(coordinator, 1),
            PensionAutoPurchaseButton(coordinator, 5),
            Lotto645AutoPurchaseButton(coordinator, 1),
            Lotto645AutoPurchaseButton(coordinator, 5),
        ]
    )


class PensionAutoPurchaseButton(ButtonEntity):
    """Buy one or five automatically selected Pension Lottery tickets."""

    _attr_device_class = ButtonDeviceClass.IDENTIFY
    _attr_icon = "mdi:ticket-confirmation-outline"

    def __init__(self, coordinator: LotteryCoordinator, games: int) -> None:
        self._coordinator = coordinator
        self._games = games
        self._attr_name = f"연금복권 720+ 자동 구매 {games}게임"
        self._attr_unique_id = (
            f"donghaeng_lottery_{coordinator.client.username}_pension_auto_{games}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"donghaeng_lottery_{coordinator.client.username}")},
            name="동행복권",
            manufacturer="동행복권",
            configuration_url="https://www.dhlottery.co.kr",
        )

    @property
    def available(self) -> bool:
        return self._coordinator.client.logged_in

    async def async_press(self) -> None:
        try:
            tickets = await self._coordinator.client.buy_pension_auto(self._games)
            await self._coordinator.async_request_refresh()
        except LotteryError:
            raise
        except Exception as err:
            raise LotteryError("연금복권 720+ 자동 구매에 실패했습니다.") from err
        message = "\n".join(
            f"{item['round']}회 {item['group']}조 {item['number']}" for item in tickets
        )
        persistent_notification.async_create(
            self.hass,
            message,
            f"연금복권 720+ 자동 구매 ({self._games}게임)",
            f"{self.unique_id}_purchase",
        )


class Lotto645AutoPurchaseButton(PensionAutoPurchaseButton):
    """Buy one or five automatically selected Lotto 6/45 games."""

    def __init__(self, coordinator: LotteryCoordinator, games: int) -> None:
        super().__init__(coordinator, games)
        self._attr_name = f"로또 6/45 자동 구매 {games}게임"
        self._attr_unique_id = (
            f"donghaeng_lottery_{coordinator.client.username}_lotto_645_auto_{games}"
        )

    async def async_press(self) -> None:
        try:
            result = await self._coordinator.client.buy_lotto_645_auto(self._games)
            await self._coordinator.async_request_refresh()
        except LotteryError:
            raise
        except Exception as err:
            raise LotteryError("로또 6/45 자동 구매에 실패했습니다.") from err
        games = result.get("arrGameChoiceNum", [])
        persistent_notification.async_create(
            self.hass,
            "\n".join(games),
            f"로또 6/45 자동 구매 ({self._games}게임)",
            f"{self.unique_id}_purchase",
        )
