"""Workmode and LED effect select entities for Avalon miners."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers import device_registry, entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import EntityCategory

from .const import DOMAIN, CONF_AVALON_CONTROL_MODE, AVALON_MODE_FULL
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)

# Workmode mapping for Avalon Nano 3s
WORK_MODES = {
    "Low": 0,
    "Mid": 1,
    "High": 2,
}
REVERSE_WORK_MODES = {v: k for k, v in WORK_MODES.items()}

# LED Effect mapping for Avalon Nano 3s
LED_EFFECTS = {
    "Stay": 1,
    "Flash": 2,
    "Breathing": 3,
    "Loop": 4,
}
REVERSE_LED_EFFECTS = {v: k for k, v in LED_EFFECTS.items()}


class AvalonCGMinerAPI:
    """CGMiner API client for Avalon miners."""

    def __init__(self, host: str, port: int = 4028, timeout: int = 10):
        """Initialize the CGMiner API client."""
        self.host = host
        self.port = port
        self.timeout = timeout

    async def _send_command(self, command: str) -> str | None:
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
            response = raw.decode("utf-8", errors="ignore").strip()
            _LOGGER.info("CGMiner command '%s' response: %s", command, response[:500] if response else "(empty)")
            return response
        except Exception as e:
            _LOGGER.error("CGMiner command '%s' failed: %s", command, e)
            return None

    async def get_workmode(self) -> int | None:
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
        _LOGGER.debug("Workmode set response: %s", raw)
        if not raw:
            return False

        # Check for success status
        return "STATUS=S" in raw or "success" in raw.lower()

    async def get_summary(self) -> dict[str, Any]:
        """Get mining summary (Best Share, Found Blocks, etc)."""
        raw = await self._send_command("summary")
        if not raw:
            return {}

        result = {}
        # Parse key=value pairs from summary response
        for match in re.finditer(r"([A-Za-z][A-Za-z0-9 %]+)=([^,|]+)", raw):
            key = match.group(1).strip()
            value = match.group(2).strip()
            try:
                # Try to convert to number
                if "." in value:
                    result[key] = float(value)
                else:
                    result[key] = int(value)
            except ValueError:
                result[key] = value
        return result

    async def get_led_state(self) -> dict[str, Any]:
        """Get LED state from estats command."""
        raw = await self._send_command("estats")
        if not raw:
            return {}

        result = {}
        # Parse LEDUser[Effect-W-Intensity-R-G-B] (WRGB format)
        match = re.search(r"LEDUser\[([^\]]+)\]", raw)
        if match:
            parts = match.group(1).split("-")
            if len(parts) >= 6:
                result = {
                    "effect": int(parts[0]),
                    "white": int(parts[1]),      # W channel (0-100)
                    "intensity": int(parts[2]),   # Overall intensity (0-100)
                    "r": int(parts[3]),
                    "g": int(parts[4]),
                    "b": int(parts[5]),
                }
        return result

    async def set_led(self, effect: int, white: int, intensity: int, r: int, g: int, b: int) -> bool:
        """Set LED using ascset command.
        
        Format: effect-W-intensity-R-G-B (WRGB LED strip)
        - effect: LED effect mode (0=off, 1=stay, 2=flash, 3=breathing, 4=loop)
        - white: White channel brightness (0-100)
        - intensity: Overall intensity/brightness (0-100)
        - r, g, b: RGB color values (0-255)
        """
        # Clamp values to valid ranges
        white = max(0, min(100, white))
        intensity = max(5, min(100, intensity))
        # Format: ascset|0,ledset,effect-W-intensity-R-G-B
        param = f"{effect}-{white}-{intensity}-{r}-{g}-{b}"
        raw = await self._send_command(f"ascset|0,ledset,{param}")
        _LOGGER.debug("LED set response: %s", raw)
        if not raw:
            return False
        # STATUS=I means info/success for ledset command
        return "STATUS=S" in raw or "STATUS=I" in raw


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

    # Check if user wants full CGMiner control for Avalon miners
    avalon_mode = config_entry.data.get(CONF_AVALON_CONTROL_MODE, AVALON_MODE_FULL)

    # Add workmode and LED effect select for Avalon Nano miners (only in full mode)
    if is_avalon_nano_miner(coordinator.miner) and avalon_mode == AVALON_MODE_FULL:
        _LOGGER.info(
            "Detected Avalon Nano miner at %s, adding workmode and LED controls (full mode)",
            coordinator.data.get("ip"),
        )
        entities.append(AvalonWorkModeSelect(coordinator))
        entities.append(AvalonLedEffectSelect(coordinator))

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
        self._current_mode: str | None = None

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


class AvalonLedEffectSelect(CoordinatorEntity[MinerCoordinator], SelectEntity):
    """Select entity for Avalon miner LED effect."""

    _attr_has_entity_name = True
    _attr_options = list(LED_EFFECTS.keys())
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MinerCoordinator):
        """Initialize the LED effect select entity."""
        super().__init__(coordinator=coordinator)
        self._api = AvalonCGMinerAPI(coordinator.data["ip"])
        self._current_effect: str | None = "Stay"
        self._led_state: dict[str, Any] = {}

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} LED Effect"

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
        return f"{self.coordinator.data['mac']}-led_effect"

    @property
    def current_option(self) -> str | None:
        """Return current LED effect."""
        led_data = self.coordinator.data.get("avalon_led") or {}
        if led_data:
            effect = led_data.get("effect", 1)
            return REVERSE_LED_EFFECTS.get(effect, "Stay")
        return self._current_effect or "Stay"

    async def async_select_option(self, option: str) -> None:
        """Change the LED effect."""
        effect_id = LED_EFFECTS.get(option)
        if effect_id is None:
            _LOGGER.warning("Unknown LED effect: %s", option)
            return

        _LOGGER.info(
            "%s: Setting LED effect to %s (id %d)",
            self.coordinator.config_entry.title,
            option,
            effect_id,
        )

        # Get current LED state to preserve white channel, intensity and color
        led_data = self.coordinator.data.get("avalon_led") or {}
        white = led_data.get("white", 100)
        intensity = led_data.get("intensity", 50)
        r = led_data.get("r", 255)
        g = led_data.get("g", 255)
        b = led_data.get("b", 255)

        success = await self._api.set_led(effect_id, white, intensity, r, g, b)
        if success:
            self._current_effect = option
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set LED effect to %s", option)

    async def async_added_to_hass(self) -> None:
        """Fetch initial LED state when entity is added."""
        await super().async_added_to_hass()
        led_state = await self._api.get_led_state()
        if led_state:
            self._led_state = led_state
            effect = led_state.get("effect", 1)
            self._current_effect = REVERSE_LED_EFFECTS.get(effect, "Stay")
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        led_data = self.coordinator.data.get("avalon_led") or {}
        if led_data:
            effect = led_data.get("effect", 1)
            self._current_effect = REVERSE_LED_EFFECTS.get(effect, "Stay")
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
