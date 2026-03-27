"""Workmode select entity for Avalon miners."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers import device_registry, entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import EntityCategory

from .const import DOMAIN
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)

# Workmode mapping for Avalon Nano 3s
WORK_MODES = {
    "Low": 0,
    "Mid": 1,
    "High": 2,
}
REVERSE_WORK_MODES = {v: k for k, v in WORK_MODES.items()}


class AvalonCGMinerAPI:
    """CGMiner API client for Avalon miners."""

    def __init__(self, host: str, port: int = 4028, timeout: int = 10):
        """Initialize the CGMiner API client."""
        self.host = host
        self.port = port
        self.timeout = timeout

    async def _send_command(self, command: str) -> Optional[str]:
        """Send a command to the CGMiner API and return the response."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
            writer.write(command.encode("utf-8"))
            await writer.drain()

            raw = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=self.timeout)
                if not chunk:
                    break
                raw += chunk

            writer.close()
            await writer.wait_closed()
            return raw.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            _LOGGER.error("CGMiner command '%s' failed: %s", command, e)
            return None

    async def get_workmode(self) -> Optional[int]:
        """Get current workmode from estats command."""
        raw = await self._send_command("estats")
        if not raw:
            return None

        # Parse WORKMODE[value] from estats response
        match = re.search(r"WORKMODE\[(\d+)\]", raw)
        if match:
            return int(match.group(1))
        return None

    async def set_workmode(self, level: int) -> bool:
        """Set workmode using ascset command."""
        raw = await self._send_command(f"ascset|0,workmode,set,{level}")
        if not raw:
            return False

        # Check for success status
        return "STATUS=S" in raw or "success" in raw.lower()


def is_avalon_nano_miner(miner) -> bool:
    """Check if miner is an Avalon Nano (supports workmode)."""
    if miner is None:
        return False
    
    miner_class_name = miner.__class__.__name__.lower()
    model = getattr(miner, "model", "") or ""
    make = getattr(miner, "make", "") or ""
    
    # Check for Avalon Nano models
    if "avalon" in miner_class_name.lower() or "avalon" in make.lower():
        if "nano" in model.lower() or "nano" in miner_class_name.lower():
            return True
    
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add select entities for passed config_entry in HA."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    await coordinator.async_config_entry_first_refresh()

    entities = []

    # Add workmode select for Avalon Nano miners
    if is_avalon_nano_miner(coordinator.miner):
        _LOGGER.info(
            "Detected Avalon Nano miner at %s, adding workmode control",
            coordinator.data.get("ip"),
        )
        entities.append(AvalonWorkModeSelect(coordinator))

    if entities:
        async_add_entities(entities)


class AvalonWorkModeSelect(CoordinatorEntity[MinerCoordinator], SelectEntity):
    """Select entity for Avalon miner workmode (Low/Mid/High)."""

    _attr_has_entity_name = True
    _attr_options = list(WORK_MODES.keys())
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MinerCoordinator):
        """Initialize the workmode select entity."""
        super().__init__(coordinator=coordinator)
        self._api = AvalonCGMinerAPI(coordinator.data["ip"])
        self._current_mode: Optional[str] = None

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} Work Mode"

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
        return f"{self.coordinator.data['mac']}-workmode"

    @property
    def current_option(self) -> str | None:
        """Return current workmode."""
        # Try to get from coordinator data first
        workmode = self.coordinator.data.get("avalon_workmode")
        if workmode is not None:
            return REVERSE_WORK_MODES.get(workmode, "Low")
        return self._current_mode or "Low"

    async def async_select_option(self, option: str) -> None:
        """Change the workmode."""
        level = WORK_MODES.get(option)
        if level is None:
            _LOGGER.warning("Unknown workmode: %s", option)
            return

        _LOGGER.info(
            "%s: Setting workmode to %s (level %d)",
            self.coordinator.config_entry.title,
            option,
            level,
        )

        success = await self._api.set_workmode(level)
        if success:
            self._current_mode = option
            self.async_write_ha_state()
            # Request coordinator refresh to update other entities
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set workmode to %s", option)

    async def async_added_to_hass(self) -> None:
        """Fetch initial workmode when entity is added."""
        await super().async_added_to_hass()
        workmode = await self._api.get_workmode()
        if workmode is not None:
            self._current_mode = REVERSE_WORK_MODES.get(workmode, "Low")
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        workmode = self.coordinator.data.get("avalon_workmode")
        if workmode is not None:
            self._current_mode = REVERSE_WORK_MODES.get(workmode, "Low")
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
