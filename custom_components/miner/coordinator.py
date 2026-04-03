"""Miner DataUpdateCoordinator."""

import asyncio
import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyasic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AVALON_MODE_FULL,
    CONF_AVALON_CONTROL_MODE,
    CONF_IP,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_RPC_PASSWORD,
    CONF_SSH_PASSWORD,
    CONF_SSH_USERNAME,
    CONF_WEB_PASSWORD,
    CONF_WEB_USERNAME,
)

_LOGGER = logging.getLogger(__name__)

# Matches iotwatt data log interval
REQUEST_REFRESH_DEFAULT_COOLDOWN = 5

DEFAULT_DATA = {
    "hostname": None,
    "mac": None,
    "make": None,
    "model": None,
    "ip": None,
    "is_mining": False,
    "fw_ver": None,
    "miner_sensors": {
        "hashrate": 0,
        "ideal_hashrate": 0,
        "active_preset_name": None,
        "temperature": 0,
        "power_limit": 0,
        "miner_consumption": 0,
        "efficiency": 0.0,
    },
    "board_sensors": {},
    "fan_sensors": {},
    "config": {},
    "avalon_workmode": None,
    "avalon_led": None,
    "avalon_best_share": None,
    "avalon_found_blocks": None,
    "avalon_asc_enabled": None,
    "vnish_preset": None,
    "vnish_best_share": None,
    "vnish_found_blocks": None,
    "bos_best_share": None,
    "bos_found_blocks": None,
}


async def _fetch_avalon_workmode(ip: str, timeout: int = 10) -> int | None:
    """Fetch workmode from Avalon miner via CGMiner API."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 4028),
            timeout=timeout,
        )
        writer.write(b"estats")
        await writer.drain()

        raw = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not chunk:
                break
            raw += chunk

        writer.close()
        await writer.wait_closed()

        response = raw.decode("utf-8", errors="ignore")
        match = re.search(r"WORKMODE\[(\d+)\]", response)
        if match:
            return int(match.group(1))
    except Exception as e:
        _LOGGER.debug("Failed to fetch Avalon workmode: %s", e)
    return None


async def _fetch_avalon_led_state(ip: str, timeout: int = 10) -> dict | None:
    """Fetch LED state from Avalon miner via CGMiner API estats command."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 4028),
            timeout=timeout,
        )
        writer.write(b"estats")
        await writer.drain()

        raw = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not chunk:
                break
            raw += chunk

        writer.close()
        await writer.wait_closed()

        response = raw.decode("utf-8", errors="ignore")

        # Parse LED data: LED[effect-W-intensity-R-G-B] (WRGB format)
        # Also check for LEDUser format
        led_match = re.search(
            r"LED(?:User)?\[(\d+)-(\d+)-(\d+)-(\d+)-(\d+)-(\d+)\]", response
        )
        if led_match:
            return {
                "effect": int(led_match.group(1)),
                "white": int(led_match.group(2)),  # W channel (0-100)
                "intensity": int(led_match.group(3)),  # Overall intensity (0-100)
                "r": int(led_match.group(4)),
                "g": int(led_match.group(5)),
                "b": int(led_match.group(6)),
            }
    except Exception as e:
        _LOGGER.debug("Failed to fetch Avalon LED state: %s", e)
    return None


async def _fetch_avalon_summary(ip: str, timeout: int = 10) -> dict | None:
    """Fetch summary data from Avalon miner via CGMiner API."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 4028),
            timeout=timeout,
        )
        writer.write(b"summary")
        await writer.drain()

        raw = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not chunk:
                break
            raw += chunk

        writer.close()
        await writer.wait_closed()

        response = raw.decode("utf-8", errors="ignore")

        result = {}

        # Parse Best Share
        best_share_match = re.search(r"Best Share=(\d+)", response)
        if best_share_match:
            result["best_share"] = int(best_share_match.group(1))

        # Parse Found Blocks
        found_blocks_match = re.search(r"Found Blocks=(\d+)", response)
        if found_blocks_match:
            result["found_blocks"] = int(found_blocks_match.group(1))

        return result if result else None
    except Exception as e:
        _LOGGER.debug("Failed to fetch Avalon summary: %s", e)
    return None


async def _fetch_avalon_asc_enabled(ip: str, timeout: int = 10) -> bool | None:
    """Fetch ASC device enabled state from Avalon miner via CGMiner API devs command."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 4028),
            timeout=timeout,
        )
        writer.write(b"devs")
        await writer.drain()

        raw = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not chunk:
                break
            raw += chunk

        writer.close()
        await writer.wait_closed()

        response = raw.decode("utf-8", errors="ignore")

        # Parse Enabled field: Enabled=Y or Enabled=N
        enabled_match = re.search(r"Enabled=([YN])", response)
        if enabled_match:
            return enabled_match.group(1) == "Y"
    except Exception as e:
        _LOGGER.debug("Failed to fetch Avalon ASC enabled state: %s", e)
    return None


def _is_avalon_nano_miner(miner) -> bool:
    """Check if miner is an Avalon Nano."""
    if miner is None:
        return False

    miner_class_name = miner.__class__.__name__.lower()
    model = str(getattr(miner, "model", "") or "").lower()
    make = str(getattr(miner, "make", "") or "").lower()

    if "avalon" in miner_class_name or "avalon" in make:
        if "nano" in model or "nano" in miner_class_name:
            return True
    return False


async def _fetch_vnish_preset(ip: str, password: str = "admin") -> str | None:
    """Fetch current VNish autotune preset name via REST API."""
    import aiohttp

    base_url = f"http://{ip}/api/v1"
    try:
        async with aiohttp.ClientSession() as session:
            # Unlock and get auth token
            async with session.post(
                f"{base_url}/unlock",
                json={"pw": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                token = (await resp.json()).get("token")
                if not token:
                    return None

            # Get settings to read current preset
            async with session.get(
                f"{base_url}/settings",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                settings = await resp.json()
                return settings.get("miner", {}).get("overclock", {}).get("preset")
    except Exception as e:
        _LOGGER.debug("Failed to fetch VNish preset: %s", e)
    return None


async def _fetch_vnish_summary(ip: str, password: str = "admin") -> dict | None:
    """Fetch summary data (Best Share, Found Blocks) from VNish miner via REST API."""
    import aiohttp

    base_url = f"http://{ip}/api/v1"
    try:
        async with aiohttp.ClientSession() as session:
            # Unlock and get auth token
            async with session.post(
                f"{base_url}/unlock",
                json={"pw": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                token = (await resp.json()).get("token")
                if not token:
                    return None

            # Get summary data
            async with session.get(
                f"{base_url}/summary",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                summary = await resp.json()
                result = {}
                # VNish API returns best_share and found_blocks in miner object
                if "miner" in summary:
                    miner_data = summary["miner"]
                    if "best_share" in miner_data:
                        result["best_share"] = int(miner_data["best_share"])
                    if "found_blocks" in miner_data:
                        result["found_blocks"] = int(miner_data["found_blocks"])
                return result if result else None
    except Exception as e:
        _LOGGER.debug("Failed to fetch VNish summary: %s", e)
    return None


async def _fetch_bos_summary(ip: str, timeout: int = 10) -> dict | None:
    """Fetch summary data (Best Share, Found Blocks) from BOS miner via CGMiner API."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 4028),
            timeout=timeout,
        )
        writer.write(b'summary')
        await writer.drain()

        raw = b""
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not chunk:
                break
            raw += chunk

        writer.close()
        await writer.wait_closed()

        response = raw.decode("utf-8", errors="ignore")

        result = {}

        # Parse Best Share
        best_share_match = re.search(r"Best Share=(\d+)", response)
        if best_share_match:
            result["best_share"] = int(best_share_match.group(1))

        # Parse Found Blocks
        found_blocks_match = re.search(r"Found Blocks=(\d+)", response)
        if found_blocks_match:
            result["found_blocks"] = int(found_blocks_match.group(1))

        return result if result else None
    except Exception as e:
        _LOGGER.debug("Failed to fetch BOS summary: %s", e)
    return None


def _is_vnish_miner(miner) -> bool:
    """Check if miner is running VNish firmware."""
    if miner is None:
        return False
    if miner.web is not None:
        return type(miner.web).__name__ == "VNishWebAPI"
    return False


def _is_bos_miner(miner) -> bool:
    """Check if miner is running BOS (Braiins OS) firmware."""
    if miner is None:
        return False
    miner_class_name = miner.__class__.__name__.lower()
    fw_ver = str(getattr(miner, "fw_ver", "") or "").lower()
    # Check for BOS/Braiins indicators
    if "bos" in miner_class_name or "braiins" in miner_class_name:
        return True
    if "bos" in fw_ver or "braiins" in fw_ver:
        return True
    # Check web API type
    if miner.web is not None:
        web_type = type(miner.web).__name__.lower()
        if "bos" in web_type or "braiins" in web_type:
            return True
    return False


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the Miner."""

    miner: "pyasic.AnyMiner" = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator object."""
        self.miner = None
        self._failure_count = 0
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=10),
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=True,
            ),
        )

    @property
    def available(self):
        """Return if device is available or not."""
        return self.miner is not None

    async def get_miner(self):
        """Get a valid Miner instance."""
        import pyasic  # lazy import to avoid blocking event loop

        miner_ip = self.config_entry.data[CONF_IP]
        miner = await pyasic.get_miner(miner_ip)
        if miner is None:
            return None

        self.miner = miner
        if self.miner.api is not None:
            if self.miner.api.pwd is not None:
                self.miner.api.pwd = self.config_entry.data.get(CONF_RPC_PASSWORD, "")

        if self.miner.web is not None:
            self.miner.web.username = self.config_entry.data.get(CONF_WEB_USERNAME, "")
            self.miner.web.pwd = self.config_entry.data.get(CONF_WEB_PASSWORD, "")

        if self.miner.ssh is not None:
            self.miner.ssh.username = self.config_entry.data.get(CONF_SSH_USERNAME, "")
            self.miner.ssh.pwd = self.config_entry.data.get(CONF_SSH_PASSWORD, "")
        return self.miner

    async def _async_update_data(self):
        """Fetch sensors from miners."""
        import pyasic  # lazy import to avoid blocking event loop

        miner = await self.get_miner()

        if miner is None:
            self._failure_count += 1

            if self._failure_count <= 3:
                _LOGGER.warning(
                    f"Miner is offline – returning zeroed data (failure {self._failure_count}/3)."
                )
                return {
                    **DEFAULT_DATA,
                    "power_limit_range": {
                        "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                        "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
                    },
                }

            raise UpdateFailed("Miner Offline (consecutive failure)")

        # At this point, miner is valid
        _LOGGER.debug(f"Found miner: {self.miner}")

        # Base data options to fetch
        data_options = [
            pyasic.DataOptions.HOSTNAME,
            pyasic.DataOptions.MAC,
            pyasic.DataOptions.IS_MINING,
            pyasic.DataOptions.FW_VERSION,
            pyasic.DataOptions.HASHRATE,
            pyasic.DataOptions.EXPECTED_HASHRATE,
            pyasic.DataOptions.HASHBOARDS,
            pyasic.DataOptions.WATTAGE,
            pyasic.DataOptions.WATTAGE_LIMIT,
            pyasic.DataOptions.FANS,
            pyasic.DataOptions.CONFIG,
        ]

        try:
            miner_data = await self.miner.get_data(include=data_options)
        except Exception as err:
            # VNish firmware has a bug with CONFIG - retry without it
            if "config" in str(err).lower():
                _LOGGER.warning(
                    f"Config fetch failed for {self.miner}, retrying without CONFIG: {err}"
                )
                data_options.remove(pyasic.DataOptions.CONFIG)
                try:
                    miner_data = await self.miner.get_data(include=data_options)
                except Exception as retry_err:
                    self._failure_count += 1
                    if self._failure_count <= 3:
                        _LOGGER.warning(
                            f"Error fetching miner data: {retry_err} – returning zeroed data (failure {self._failure_count}/3)."
                        )
                        return {
                            **DEFAULT_DATA,
                            "power_limit_range": {
                                "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                                "max": self.config_entry.data.get(
                                    CONF_MAX_POWER, 10000
                                ),
                            },
                        }
                    _LOGGER.exception(retry_err)
                    raise UpdateFailed from retry_err
            else:
                self._failure_count += 1

                if self._failure_count <= 3:
                    _LOGGER.warning(
                        f"Error fetching miner data: {err} – returning zeroed data (failure {self._failure_count}/3)."
                    )
                    return {
                        **DEFAULT_DATA,
                        "power_limit_range": {
                            "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                            "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
                        },
                    }

                _LOGGER.exception(err)
                raise UpdateFailed from err

        _LOGGER.debug(f"Got data: {miner_data}")

        # Success: reset the failure count
        self._failure_count = 0

        def normalize_hashrate_to_th(value):
            """Normalize hashrate to TH/s.

            pyasic may return hashrate in different units (H/s, GH/s, TH/s).
            If the value is unreasonably high (>1 million), assume it's in H/s
            and convert to TH/s by dividing by 10^12.
            """
            if value is None:
                return None
            value = float(value)
            # If hashrate > 1 million TH/s, it's clearly in wrong unit (H/s)
            if value > 1_000_000:
                # Convert H/s to TH/s
                value = value / 1_000_000_000_000
            return round(value, 2)

        try:
            hashrate = normalize_hashrate_to_th(miner_data.hashrate)
        except TypeError:
            hashrate = None

        try:
            expected_hashrate = normalize_hashrate_to_th(miner_data.expected_hashrate)
        except TypeError:
            expected_hashrate = None

        # pyasic uses raw hashrate for efficiency_fract; if the API reports H/s in a
        # shape that doesn't match TH/s, the ratio can round to 0.0 while normalized
        # hashrate (above) matches the miner UI. Prefer W / TH/s from normalized data.
        efficiency: float | None
        try:
            w = miner_data.wattage
            if (
                w is not None
                and hashrate is not None
                and float(hashrate) > 0
            ):
                efficiency = round(float(w) / float(hashrate), 2)
            else:
                efficiency = miner_data.efficiency_fract
        except (TypeError, ValueError, ZeroDivisionError):
            efficiency = miner_data.efficiency_fract

        try:
            active_preset = miner_data.config.mining_mode.active_preset.name
        except AttributeError:
            active_preset = None

        data = {
            "hostname": miner_data.hostname,
            "mac": miner_data.mac,
            "make": miner_data.make,
            "model": miner_data.model,
            "ip": self.miner.ip,
            "is_mining": miner_data.is_mining,
            "fw_ver": miner_data.fw_ver,
            "miner_sensors": {
                "hashrate": hashrate,
                "ideal_hashrate": expected_hashrate,
                "active_preset_name": active_preset,
                "temperature": miner_data.temperature_avg,
                "power_limit": miner_data.wattage_limit,
                "miner_consumption": miner_data.wattage,
                "efficiency": efficiency,
            },
            "board_sensors": {
                board.slot: {
                    "board_temperature": board.temp,
                    "chip_temperature": board.chip_temp,
                    "board_hashrate": round(float(board.hashrate or 0), 2),
                }
                for board in miner_data.hashboards
            },
            "fan_sensors": {
                idx: {"fan_speed": fan.speed} for idx, fan in enumerate(miner_data.fans)
            },
            "config": miner_data.config,
            "power_limit_range": {
                "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
                "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
            },
            "avalon_workmode": None,
            "avalon_led": None,
            "avalon_best_share": None,
            "avalon_found_blocks": None,
            "avalon_asc_enabled": None,
            "vnish_preset": None,
            "vnish_best_share": None,
            "vnish_found_blocks": None,
            "bos_best_share": None,
            "bos_found_blocks": None,
        }

        # Fetch workmode for Avalon Nano miners (only in full CGMiner mode)
        avalon_mode = self.config_entry.data.get(
            CONF_AVALON_CONTROL_MODE, AVALON_MODE_FULL
        )
        if _is_avalon_nano_miner(self.miner) and avalon_mode == AVALON_MODE_FULL:
            workmode = await _fetch_avalon_workmode(self.miner.ip)
            data["avalon_workmode"] = workmode
            # Also update active_preset_name for sensor display
            if workmode is not None:
                workmode_names = {0: "Low", 1: "Mid", 2: "High"}
                data["miner_sensors"]["active_preset_name"] = workmode_names.get(
                    workmode, "Unknown"
                )

            # Fetch LED state
            led_state = await _fetch_avalon_led_state(self.miner.ip)
            if led_state:
                data["avalon_led"] = led_state

            # Fetch summary data (Best Share, Found Blocks)
            summary = await _fetch_avalon_summary(self.miner.ip)
            if summary:
                data["avalon_best_share"] = summary.get("best_share")
                data["avalon_found_blocks"] = summary.get("found_blocks")

            # Fetch ASC enabled state (for mining switch)
            asc_enabled = await _fetch_avalon_asc_enabled(self.miner.ip)
            if asc_enabled is not None:
                data["avalon_asc_enabled"] = asc_enabled

        # Fetch VNish preset for VNish firmware miners
        if (
            self.miner.web is not None
            and type(self.miner.web).__name__ == "VNishWebAPI"
        ):
            vnish_preset = await _fetch_vnish_preset(
                self.miner.ip,
                self.config_entry.data.get(CONF_WEB_PASSWORD, "admin"),
            )
            if vnish_preset:
                data["vnish_preset"] = vnish_preset

        # Fetch VNish preset and summary for VNish firmware miners
        if _is_vnish_miner(self.miner):
            vnish_preset = await _fetch_vnish_preset(
                self.miner.ip,
                self.config_entry.data.get(CONF_WEB_PASSWORD, "admin"),
            )
            if vnish_preset:
                data["vnish_preset"] = vnish_preset

            # Fetch VNish summary data (Best Share, Found Blocks)
            vnish_summary = await _fetch_vnish_summary(
                self.miner.ip,
                self.config_entry.data.get(CONF_WEB_PASSWORD, "admin"),
            )
            if vnish_summary:
                data["vnish_best_share"] = vnish_summary.get("best_share")
                data["vnish_found_blocks"] = vnish_summary.get("found_blocks")

        # Fetch BOS summary data (Best Share, Found Blocks) for BOS firmware miners
        if _is_bos_miner(self.miner):
            bos_summary = await _fetch_bos_summary(self.miner.ip)
            if bos_summary:
                data["bos_best_share"] = bos_summary.get("best_share")
                data["bos_found_blocks"] = bos_summary.get("found_blocks")

        return data