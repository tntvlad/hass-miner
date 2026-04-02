"""Support for Miner shutdown."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import AVALON_MODE_FULL, CONF_AVALON_CONTROL_MODE, DOMAIN
from .coordinator import MinerCoordinator, _is_avalon_nano_miner

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    created = set()

    @callback
    def _create_entity(key: str):
        """Create a sensor entity."""
        created.add(key)

    await coordinator.async_config_entry_first_refresh()

    entities = []

    # Standard miner active switch (uses pyasic)
    if coordinator.miner.supports_shutdown:
        entities.append(MinerActiveSwitch(coordinator=coordinator))

    # Check if user wants full CGMiner control for Avalon miners
    avalon_mode = config_entry.data.get(CONF_AVALON_CONTROL_MODE, AVALON_MODE_FULL)

    # Avalon Nano 3s mining switch (uses CGMiner API) - only in full mode
    if _is_avalon_nano_miner(coordinator.miner) and avalon_mode == AVALON_MODE_FULL:
        entities.append(AvalonMiningSwitch(coordinator=coordinator))

    if entities:
        async_add_entities(entities)


class MinerActiveSwitch(CoordinatorEntity[MinerCoordinator], SwitchEntity):
    """Defines a Miner Switch to pause and unpause the miner."""

    def __init__(
        self,
        coordinator: MinerCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-active"
        self._attr_is_on = self.coordinator.data["is_mining"]
        self.updating_switch = False
        self._last_mining_mode = None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} active"

    @property
    def device_info(self) -> entity.DeviceInfo:
        """Return device info."""
        return entity.DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.data["mac"])},
            manufacturer=self.coordinator.data["make"],
            model=self.coordinator.data["model"],
            sw_version=self.coordinator.data["fw_ver"],
            name=f"{self.coordinator.config_entry.title}",
        )

    async def async_turn_on(self) -> None:
        """Turn on miner."""
        miner = self.coordinator.miner
        _LOGGER.debug(f"{self.coordinator.config_entry.title}: Resume mining.")
        if not miner.supports_shutdown:
            raise TypeError(f"{miner}: Shutdown not supported.")
        self._attr_is_on = True
        try:
            await miner.resume_mining()
        except Exception as err:
            # VNish and some firmwares return empty response but still work
            _LOGGER.debug(
                f"{self.coordinator.config_entry.title}: Resume API returned error (expected for VNish): {err}"
            )

        # Try to restore mining mode config - skip if not supported or fails
        try:
            if miner.supports_power_modes and self._last_mining_mode:
                config = await miner.get_config()
                config.mining_mode = self._last_mining_mode
                await miner.send_config(config)
        except Exception as err:
            _LOGGER.debug(
                f"{self.coordinator.config_entry.title}: Could not restore config (expected for some firmwares): {err}"
            )

        self.updating_switch = True
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off miner."""
        miner = self.coordinator.miner
        _LOGGER.debug(f"{self.coordinator.config_entry.title}: Stop mining.")
        if not miner.supports_shutdown:
            raise TypeError(f"{miner}: Shutdown not supported.")

        # Try to save mining mode config - skip if not supported or fails
        try:
            if miner.supports_power_modes:
                self._last_mining_mode = (
                    self.coordinator.data.get("config", {}).mining_mode
                    if self.coordinator.data.get("config")
                    else None
                )
        except Exception:
            self._last_mining_mode = None

        self._attr_is_on = False
        try:
            await miner.stop_mining()
        except Exception as err:
            # VNish and some firmwares return empty response but still work
            _LOGGER.debug(
                f"{self.coordinator.config_entry.title}: Stop API returned error (expected for VNish): {err}"
            )
        self.updating_switch = True
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        is_mining = self.coordinator.data["is_mining"]
        if is_mining is not None:
            if self.updating_switch:
                if is_mining == self._attr_is_on:
                    self.updating_switch = False
            if not self.updating_switch:
                self._attr_is_on = is_mining

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available


class AvalonMiningSwitch(CoordinatorEntity[MinerCoordinator], SwitchEntity):
    """Switch to pause/resume mining on Avalon Nano 3s via CGMiner API."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator: MinerCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{self.coordinator.data['mac']}-avalon-mining"
        # Get initial state from coordinator data, default to True
        asc_enabled = self.coordinator.data.get("avalon_asc_enabled")
        self._attr_is_on = asc_enabled if asc_enabled is not None else True
        self._updating_switch = False

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Mining"

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

    async def _send_cgminer_command(self, command: str) -> bool:
        """Send a command to CGMiner API and return success status."""
        ip = self.coordinator.data["ip"]
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 4028),
                timeout=10,
            )
            writer.write(command.encode())
            await writer.drain()

            raw = b""
            with contextlib.suppress(asyncio.TimeoutError):
                raw = await asyncio.wait_for(reader.read(4096), timeout=5)

            writer.close()
            await writer.wait_closed()

            response = raw.decode("utf-8", errors="ignore")
            _LOGGER.debug("CGMiner response for '%s': %s", command, response)

            # Check for success - STATUS=S (success) or STATUS=I (info)
            # Also check for error messages
            if "STATUS=E" in response:
                _LOGGER.warning(
                    "CGMiner command '%s' returned error: %s", command, response
                )
                return False
            return "STATUS=S" in response or "STATUS=I" in response or len(response) > 0

        except Exception as e:
            _LOGGER.error("Failed to send CGMiner command '%s': %s", command, e)
            return False

    async def async_turn_on(self) -> None:
        """Enable mining (ascenable)."""
        _LOGGER.info(
            "%s: Enabling mining via CGMiner API", self.coordinator.config_entry.title
        )

        success = await self._send_cgminer_command("ascenable|0")
        if success:
            self._attr_is_on = True
            self._updating_switch = True
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to enable mining")

    async def async_turn_off(self) -> None:
        """Disable mining (ascdisable)."""
        _LOGGER.info(
            "%s: Disabling mining via CGMiner API", self.coordinator.config_entry.title
        )

        success = await self._send_cgminer_command("ascdisable|0")
        if success:
            self._attr_is_on = False
            self._updating_switch = True
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to disable mining")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check ASC enabled state from coordinator data (from devs command)
        asc_enabled = self.coordinator.data.get("avalon_asc_enabled")
        if asc_enabled is not None:
            # If we just sent a command, wait for the state to match before accepting updates
            if self._updating_switch:
                if asc_enabled == self._attr_is_on:
                    self._updating_switch = False
            else:
                self._attr_is_on = asc_enabled
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
