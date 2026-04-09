"""Support for Bitcoin ASIC miners."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    pass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.components.sensor import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_WEB_PASSWORD, CONF_WEB_USERNAME, DOMAIN
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

    # Skip power limit slider for VNish miners — use VNish Preset select instead
    is_vnish = (
        coordinator.miner.web is not None
        and type(coordinator.miner.web).__name__ == "VNishWebAPI"
    )
    if coordinator.miner.supports_autotuning and not is_vnish:
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
        self.entity_description = entity_description

    @property
    def native_value(self) -> float | None:
        """Return current power limit from coordinator data."""
        return self.coordinator.data["miner_sensors"]["power_limit"]

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

    def _is_bos_miner(self) -> bool:
        """Check if miner is running BrainOS (Braiins OS) firmware."""
        miner = self.coordinator.miner
        if miner is None:
            return False

        # Check miner class name
        miner_class_name = miner.__class__.__name__
        if "BOSer" in miner_class_name or "BOS" in miner_class_name:
            return True

        # Check web API type (BOSMinerWebAPI or similar)
        if miner.web is not None:
            web_type = type(miner.web).__name__
            if "BOS" in web_type or "Braiins" in web_type:
                return True

        # Check firmware version string for BrainOS patterns
        fw_ver = str(self.coordinator.data.get("fw_ver", "") or "").lower()
        # BrainOS firmware often has patterns like "2026-02-13-0-db69f9bc-26.01-plus"
        # or contains "braiins", "bos", etc.
        if any(pattern in fw_ver for pattern in ["braiins", "bos+", "bos-", "-plus"]):
            return True

        # Check if firmware looks like a BrainOS date-based version
        # Pattern: YYYY-MM-DD followed by hash and version
        import re
        if re.match(r"\d{4}-\d{2}-\d{2}-\d+-[a-f0-9]+-\d+\.\d+", fw_ver):
            return True

        return False

    def _bos_supports_rest_api(self) -> bool:
        """Check if BOS firmware supports REST API (introduced in 23.03).

        Older firmware like 22.08.1 uses CGminer API instead.
        REST API was introduced in BOS version 23.03.

        Firmware version formats:
        - Old style: "22.08.1" (YY.MM.patch)
        - New style: "2026-02-13-0-db69f9bc-26.01-plus" (date-hash-YY.MM-edition)
        """
        import re

        fw_ver = str(self.coordinator.data.get("fw_ver", "") or "")

        # Try to extract version number
        # New format: "2026-02-13-0-db69f9bc-26.01-plus" -> extract "26.01"
        new_format_match = re.search(r"-(\d{2})\.(\d{2})(?:-|$)", fw_ver)
        if new_format_match:
            year = int(new_format_match.group(1))
            month = int(new_format_match.group(2))
            # REST API introduced in 23.03
            if year > 23 or (year == 23 and month >= 3):
                return True
            return False

        # Old format: "22.08.1" or "22.08" -> extract year and month
        old_format_match = re.match(r"^(\d{2})\.(\d{2})", fw_ver)
        if old_format_match:
            year = int(old_format_match.group(1))
            month = int(old_format_match.group(2))
            # REST API introduced in 23.03
            if year > 23 or (year == 23 and month >= 3):
                return True
            return False

        # Unknown format - assume modern firmware supports REST API
        _LOGGER.debug(f"Unknown BOS firmware format: {fw_ver}, assuming REST API support")
        return True

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

        # Check miner type and use appropriate API
        miner_class_name = miner.__class__.__name__
        web_type = type(miner.web).__name__ if miner.web else "None"
        fw_ver = self.coordinator.data.get("fw_ver", "")
        is_bos = self._is_bos_miner()
        supports_rest = self._bos_supports_rest_api() if is_bos else False

        _LOGGER.debug(
            f"Miner class: {miner_class_name}, web: {web_type}, fw: {fw_ver}, "
            f"is_bos: {is_bos}, supports_rest_api: {supports_rest}"
        )

        if is_bos and supports_rest:
            # BOS 23.03+ - use REST API to avoid restart
            result = await self._set_power_via_bos_api(int(value))
        elif is_bos and not supports_rest:
            # BOS <23.03 - use GraphQL API
            result = await self._set_power_via_graphql(int(value))
        else:
            # Use pyasic's native set_power_limit for non-BOS miners
            result = await miner.set_power_limit(int(value))

        if not result:
            raise pyasic.APIError("Failed to set wattage.")

        await self.coordinator.async_request_refresh()

    async def _set_power_via_graphql(self, watt: int) -> bool:
        """Set power target using GraphQL API (for older BOS firmware <23.03).

        Older BOS firmware uses GraphQL at /graphql endpoint.
        """
        ip = self.coordinator.data["ip"]
        username = self.coordinator.config_entry.data.get(CONF_WEB_USERNAME, "root")
        password = self.coordinator.config_entry.data.get(CONF_WEB_PASSWORD, "root")

        _LOGGER.debug(
            f"BOS GraphQL: ip={ip}, username={username}, password={'*' * len(password) if password else 'None'}"
        )

        # GraphQL login mutation
        login_query = """
mutation ($username: String!, $password: String!) {
  auth {
    login(username: $username, password: $password) {
      ... on Error {
        message
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

        # GraphQL power update mutation
        power_query = """
mutation ($tuneInput: AutotuningIn!, $apply: Boolean!) {
  bosminer {
    config {
      updateAutotuning(input: $tuneInput, apply: $apply) {
        ... on AttributeError {
          message
          __typename
        }
        ... on AutotuningError {
          mode
          message
          __typename
        }
        ... on AutotuningOut {
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

        try:
            # Use cookie jar to preserve session cookies
            jar = aiohttp.CookieJar(unsafe=True)  # unsafe=True allows cookies for IP addresses
            async with aiohttp.ClientSession(cookie_jar=jar) as session:
                # Login first
                async with session.post(
                    f"http://{ip}/graphql",
                    json={
                        "query": login_query,
                        "variables": {"username": username, "password": password}
                    },
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(f"BOS GraphQL login failed: {resp.status}")
                        return False
                    login_data = await resp.json()
                    _LOGGER.debug(f"BOS GraphQL login response: {login_data}")
                    _LOGGER.debug(f"BOS GraphQL cookies after login: {session.cookie_jar.filter_cookies(f'http://{ip}')}")

                    # Check for login errors
                    auth_result = login_data.get("data", {}).get("auth", {}).get("login", {})
                    if auth_result.get("__typename") == "Error":
                        _LOGGER.error(f"BOS GraphQL login error: {auth_result.get('message')}")
                        return False

                # Set power target
                async with session.post(
                    f"http://{ip}/graphql",
                    json={
                        "query": power_query,
                        "variables": {
                            "tuneInput": {"powerTarget": watt},
                            "apply": True
                        }
                    },
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(f"BOS GraphQL set power failed: {resp.status}")
                        return False
                    result = await resp.json()
                    _LOGGER.debug(f"BOS GraphQL set power response: {result}")

                    # Check for success
                    if "errors" in result:
                        _LOGGER.error(f"BOS GraphQL error: {result['errors']}")
                        return False

                    config = result.get("data", {}).get("bosminer", {}).get("config", {})
                    update_result = config.get("updateAutotuning", {})
                    if update_result.get("__typename") == "AutotuningOut":
                        _LOGGER.debug(f"BOS GraphQL set power to {watt}W successfully")
                        return True
                    elif "message" in update_result:
                        _LOGGER.error(f"BOS GraphQL error: {update_result['message']}")
                        return False

                    return True

        except Exception as e:
            _LOGGER.error(f"BOS GraphQL error: {e}")
            return False

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

                # Set power target (token only, no Bearer prefix for BOS API)
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
