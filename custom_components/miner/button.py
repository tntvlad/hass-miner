"""Support for Avalon Miner buttons (Reboot)."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator, _is_avalon_nano_miner

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Avalon miner buttons from config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    await coordinator.async_config_entry_first_refresh()

    # Only add reboot button for Avalon Nano miners
    if _is_avalon_nano_miner(coordinator.miner):
        async_add_entities([AvalonRebootButton(coordinator)])


class AvalonRebootButton(CoordinatorEntity[MinerCoordinator], ButtonEntity):
    """Button entity to reboot Avalon miner."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        """Initialize the reboot button."""
        super().__init__(coordinator=coordinator)

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Reboot"

    @property
    def unique_id(self) -> str | None:
        """Return device UUID."""
        return f"{self.coordinator.data['mac']}-reboot"

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

    async def async_press(self) -> None:
        """Handle the button press - reboot the miner."""
        ip = self.coordinator.data["ip"]
        _LOGGER.info(
            "%s: Rebooting miner at %s", self.coordinator.config_entry.title, ip
        )

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 4028),
                timeout=10,
            )
            # CGMiner restart command
            writer.write(b"restart")
            await writer.drain()

            # Read response (may be empty or disconnected on restart)
            try:
                raw = await asyncio.wait_for(reader.read(4096), timeout=5)
                response = raw.decode("utf-8", errors="ignore")
                _LOGGER.debug("Reboot response: %s", response)
            except asyncio.TimeoutError:
                _LOGGER.debug("No response from restart command (expected)")

            writer.close()
            await writer.wait_closed()

            _LOGGER.info(
                "%s: Reboot command sent successfully",
                self.coordinator.config_entry.title,
            )

        except Exception as e:
            _LOGGER.error("Failed to reboot miner: %s", e)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
