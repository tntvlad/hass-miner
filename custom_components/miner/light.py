"""Support for Avalon Miner LED light control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator, _is_avalon_nano_miner
from .select import AvalonCGMinerAPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Avalon LED light from config entry."""
    coordinator: MinerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    await coordinator.async_config_entry_first_refresh()

    # Only add LED light for Avalon Nano miners
    if _is_avalon_nano_miner(coordinator.miner):
        async_add_entities([AvalonLedLight(coordinator)])


class AvalonLedLight(CoordinatorEntity[MinerCoordinator], LightEntity):
    """Representation of an Avalon miner LED light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature(0)

    def __init__(self, coordinator: MinerCoordinator) -> None:
        """Initialize the LED light."""
        super().__init__(coordinator=coordinator)
        self._api = AvalonCGMinerAPI(coordinator.data["ip"])
        self._attr_brightness: int = 255
        self._attr_rgb_color: tuple[int, int, int] = (255, 255, 255)
        self._is_on: bool = True
        self._effect: int = 1  # Default: Stay (on)

    @property
    def name(self) -> str | None:
        """Return name of the entity."""
        return f"{self.coordinator.config_entry.title} LED"

    @property
    def unique_id(self) -> str | None:
        """Return device UUID."""
        return f"{self.coordinator.data['mac']}-led_light"

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
    def is_on(self) -> bool:
        """Return True if the light is on."""
        led_data = self.coordinator.data.get("avalon_led") or {}
        if led_data:
            effect = led_data.get("effect", 1)
            return effect != 0  # 0 = Off
        return self._is_on

    @property
    def brightness(self) -> int:
        """Return the brightness of the light (0-255)."""
        led_data = self.coordinator.data.get("avalon_led") or {}
        if led_data:
            # Avalon intensity is 0-100, convert to 0-255
            avalon_intensity = led_data.get("intensity", 50)
            return int((avalon_intensity / 100) * 255)
        return self._attr_brightness

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color of the light."""
        led_data = self.coordinator.data.get("avalon_led") or {}
        if led_data:
            r = led_data.get("r", 255)
            g = led_data.get("g", 255)
            b = led_data.get("b", 255)
            return (r, g, b)
        return self._attr_rgb_color

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        led_data = self.coordinator.data.get("avalon_led") or {}

        # Get current values or defaults (WRGB format: effect-W-intensity-R-G-B)
        current_white = led_data.get("white", 100) if led_data else 100
        current_intensity = led_data.get("intensity", 50) if led_data else 50
        current_r = led_data.get("r", 255) if led_data else 255
        current_g = led_data.get("g", 255) if led_data else 255
        current_b = led_data.get("b", 255) if led_data else 255
        current_effect = led_data.get("effect", 1) if led_data else 1

        # If light was off, turn it on with Stay effect
        if current_effect == 0:
            current_effect = 1

        # Process brightness if provided (controls intensity, not white channel)
        if ATTR_BRIGHTNESS in kwargs:
            # Convert from 0-255 to 5-100 (Avalon min intensity is 5)
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            current_intensity = max(5, int((ha_brightness / 255) * 100))
            self._attr_brightness = ha_brightness

        # Process RGB color if provided
        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            current_r = r
            current_g = g
            current_b = b
            self._attr_rgb_color = (r, g, b)

        _LOGGER.info(
            "%s: Setting LED - effect=%d, white=%d, intensity=%d, r=%d, g=%d, b=%d",
            self.coordinator.config_entry.title,
            current_effect,
            current_white,
            current_intensity,
            current_r,
            current_g,
            current_b,
        )

        success = await self._api.set_led(
            current_effect, current_white, current_intensity,
            current_r, current_g, current_b
        )

        if success:
            self._is_on = True
            self._effect = current_effect
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on LED")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light by setting effect to 0."""
        led_data = self.coordinator.data.get("avalon_led") or {}

        # Preserve current settings but set effect to 0 (off)
        white = led_data.get("white", 100) if led_data else 100
        intensity = led_data.get("intensity", 50) if led_data else 50
        r = led_data.get("r", 255) if led_data else 255
        g = led_data.get("g", 255) if led_data else 255
        b = led_data.get("b", 255) if led_data else 255

        _LOGGER.info("%s: Turning off LED (setting effect=0)", self.coordinator.config_entry.title)

        success = await self._api.set_led(0, white, intensity, r, g, b)

        if success:
            self._is_on = False
            self._effect = 0
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off LED")

    async def async_added_to_hass(self) -> None:
        """Fetch initial LED state when entity is added."""
        await super().async_added_to_hass()
        led_state = await self._api.get_led_state()
        if led_state:
            self._effect = led_state.get("effect", 1)
            self._is_on = self._effect != 0
            intensity = led_state.get("intensity", 50)
            self._attr_brightness = int((intensity / 100) * 255)
            self._attr_rgb_color = (
                led_state.get("r", 255),
                led_state.get("g", 255),
                led_state.get("b", 255),
            )
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        led_data = self.coordinator.data.get("avalon_led") or {}
        if led_data:
            self._effect = led_data.get("effect", 1)
            self._is_on = self._effect != 0
            intensity = led_data.get("intensity", 50)
            self._attr_brightness = int((intensity / 100) * 255)
            self._attr_rgb_color = (
                led_data.get("r", 255),
                led_data.get("g", 255),
                led_data.get("b", 255),
            )
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available or not."""
        return self.coordinator.available
