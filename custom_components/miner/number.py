"""Support for Bitcoin ASIC miners."""
from __future__ import annotations

import logging
import aiohttp
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyasic

from homeassistant.components.number import NumberEntityDescription, NumberDeviceClass
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers import entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import EntityCategory
from homeassistant.const import UnitOfPower

from .const import DOMAIN, CONF_WEB_USERNAME, CONF_WEB_PASSWORD
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)


NUMBER_DESCRIPTION_KEY_MAP: dict[str, NumberEntityDescription] = {
    "power_limit": NumberEntityDescription(
        key="Power Limit",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=NumberDeviceClass.POWER,
        entity_category=EntityCategory.CONFIG,
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    await coordinator.async_config_entry_first_refresh()
    if coordinator.miner.supports_autotuning:
        async_add_entities(
            [
                MinerPowerLimitNumber(
                    coordinator=coordinator,
                    entity_description=NUMBER_DESCRIPTION_KEY_MAP["power_limit"],
                )
            ]
        )


class MinerPowerLimitNumber(CoordinatorEntity[MinerCoordinator], NumberEntity):
    """Defines a Miner Number to set the Power Limit of the Miner."""

    def __init__(
        self, coordinator: MinerCoordinator, entity_description: NumberEntityDescription
    ):
        """Initialize the PowerLimit entity."""
        super().__init__(coordinator=coordinator)
        self._attr_native_value = self.coordinator.data["miner_sensors"]["power_limit"]
        self.entity_description = entity_description

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Power Limit"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            connections={
                ("ip", self.coordinator.data["ip"]),
                (device_registry.CONNECTION_NETWORK_MAC, self.coordinator.data["mac"]),
            },
            configuration_url=f"http://{self.coordinator.data['ip']}",
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.config_entry.title}",
        )

    @property
    def unique_id(self) -> str | None:
        """Return device UUID."""
        return f"{self.coordinator.data['mac']}-power_limit"

    @property
    def native_min_value(self) -> float | None:
        """Return device minimum value."""
        return self.coordinator.data["power_limit_range"]["min"]

    @property
    def native_max_value(self) -> float | None:
        """Return device maximum value."""
        return self.coordinator.data["power_limit_range"]["max"]

    @property
    def native_step(self) -> float | None:
        """Return device increment step."""
        return 100

    @property
    def native_unit_of_measurement(self):
        """Return device unit of measurement."""
        return "W"

    async def async_set_native_value(self, value):
        """Update the current value."""
        import pyasic  # lazy import to avoid blocking event loop

        miner = self.coordinator.miner

        _LOGGER.debug(
            f"{self.coordinator.config_entry.title}: setting power limit to {value}."
        )

        if not miner.supports_autotuning:
            raise TypeError(
                f"{self.coordinator.config_entry.title}: Tuning not supported."
            )

        # Check if this is a BOS miner - use REST API to avoid restart
        miner_class_name = miner.__class__.__name__
        if "BOSer" in miner_class_name or "BOS" in miner_class_name:
            result = await self._set_power_via_bos_api(int(value))
        else:
            result = await miner.set_power_limit(int(value))

        if not result:
            raise pyasic.APIError("Failed to set wattage.")

        self._attr_native_value = value
        self.async_write_ha_state()

    async def _set_power_via_bos_api(self, watt: int) -> bool:
        """Set power target using BOS REST API (doesn't restart miner)."""
        ip = self.coordinator.data["ip"]
        username = self.coordinator.config_entry.data.get(CONF_WEB_USERNAME, "root")
        password = self.coordinator.config_entry.data.get(CONF_WEB_PASSWORD, "root")

        try:
            async with aiohttp.ClientSession() as session:
                # Login to get auth token
                async with session.post(
                    f"http://{ip}/api/v1/auth/login",
                    json={"username": username, "password": password},
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(f"BOS API login failed: {resp.status}")
                        return False
                    login_data = await resp.json()
                    token = login_data.get("token")

                # Set power target (no "Bearer" prefix for BOS API)
                async with session.put(
                    f"http://{ip}/api/v1/performance/power-target",
                    json={"watt": watt},
                    headers={"Authorization": token},
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(f"BOS API set power failed: {resp.status}")
                        return False
                    _LOGGER.debug(f"BOS API set power to {watt}W successfully")
                    return True

        except Exception as e:
            _LOGGER.error(f"BOS API error: {e}")
            return False

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data["miner_sensors"]["power_limit"] is not None:
            self._attr_native_value = self.coordinator.data["miner_sensors"][
                "power_limit"
            ]

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
