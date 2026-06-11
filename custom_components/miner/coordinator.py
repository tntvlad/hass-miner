"""Miner DataUpdateCoordinator."""

import asyncio
import copy
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
    AVAILABILITY_FAILURE_THRESHOLD,
    AVALON_MODE_FULL,
    CONF_AVALON_CONTROL_MODE,
    CONF_CACHED_PROFILE,
    CONF_IP,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_RPC_PASSWORD,
    CONF_SSH_PASSWORD,
    CONF_SSH_USERNAME,
    CONF_WEB_PASSWORD,
    CONF_WEB_USERNAME,
    MINER_DETECTION_TIMEOUT,
    TRANSIENT_FAILURE_GRACE,
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
    "vnish_throttle": None,
    "vnish_miner_state": None,
    "vnish_voltage": None,
    "vnish_freq": None,
    "vnish_min_voltage": None,
    "vnish_max_voltage": None,
    "vnish_min_freq": None,
    "vnish_max_freq": None,
    "bos_best_share": None,
    "bos_found_blocks": None,
    "bitaxe_best_share": None,
    "bitaxe_found_blocks": None,
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
                    # VNish >= 1.3.3: miner_status carries the throttle level
                    # (percent of full power, e.g. 100 = unthrottled) and the
                    # miner state (mining/paused/stopped/...).
                    status = miner_data.get("miner_status") or {}
                    if "throttled" in status:
                        result["throttled"] = status.get("throttled")
                    if "miner_state" in status:
                        result["miner_state"] = status.get("miner_state")
                return result if result else None
    except Exception as e:
        _LOGGER.debug("Failed to fetch VNish summary: %s", e)
    return None


async def _fetch_vnish_temperatures(ip: str, password: str = "admin") -> dict | None:
    """Fetch temperature data from VNish miner via REST API (bypassing pyasic).

    Returns a dict with board temperatures (min and max):
    {
        0: {
            "board_temperature": 62, "board_temperature_min": 53,
            "chip_temperature": 77, "chip_temperature_min": 68
        },
        ...
    }

    Note: VNish API structure - temps are nested objects:
    - pcb_temp: {"min": 53, "max": 62}  (board/PCB temperature)
    - chip_temp: {"min": 68, "max": 77} (chip temperature, always higher)

    We extract both min and max values for display.
    """
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
                    _LOGGER.debug("VNish %s: unlock failed with status %s", ip, resp.status)
                    return None
                token = (await resp.json()).get("token")
                if not token:
                    _LOGGER.debug("VNish %s: no token in unlock response", ip)
                    return None

            # Get summary data which includes hashboard temperatures
            async with session.get(
                f"{base_url}/summary",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("VNish %s: summary failed with status %s", ip, resp.status)
                    return None
                summary = await resp.json()

                _LOGGER.debug("VNish %s: raw summary keys: %s", ip, list(summary.keys()))

                result = {}
                # VNish API returns hashboards in miner.chains array
                if "miner" in summary and "chains" in summary["miner"]:
                    chains = summary["miner"]["chains"]
                    _LOGGER.debug("VNish %s: found %d chains in miner.chains", ip, len(chains))
                    for chain in chains:
                        # VNish uses 1-based chain IDs, convert to 0-based slot index
                        chain_id = chain.get("id", 0)
                        slot = chain_id - 1 if chain_id > 0 else 0

                        # VNish API: temps are nested objects with min/max
                        # pcb_temp: {"min": 53, "max": 62}
                        # chip_temp: {"min": 68, "max": 77}
                        pcb_temp_obj = chain.get("pcb_temp", {})
                        chip_temp_obj = chain.get("chip_temp", {})

                        # Extract min and max temps (or 0 if not present)
                        pcb_temp_max = pcb_temp_obj.get("max", 0) if isinstance(pcb_temp_obj, dict) else 0
                        pcb_temp_min = pcb_temp_obj.get("min", 0) if isinstance(pcb_temp_obj, dict) else 0
                        chip_temp_max = chip_temp_obj.get("max", 0) if isinstance(chip_temp_obj, dict) else 0
                        chip_temp_min = chip_temp_obj.get("min", 0) if isinstance(chip_temp_obj, dict) else 0

                        # Hydro miners expose water cooling temperatures per chain
                        water_inlet = chain.get("inlet_water_temp")
                        water_outlet = chain.get("outlet_water_temp")

                        _LOGGER.debug(
                            "VNish %s chain id=%d slot=%d: pcb=%s/%s, chip=%s/%s, water=%s/%s",
                            ip, chain_id, slot, pcb_temp_min, pcb_temp_max, chip_temp_min, chip_temp_max,
                            water_inlet, water_outlet,
                        )

                        result[slot] = {
                            "board_temperature": pcb_temp_max,
                            "board_temperature_min": pcb_temp_min,
                            "chip_temperature": chip_temp_max,
                            "chip_temperature_min": chip_temp_min,
                            "water_inlet_temperature": water_inlet,
                            "water_outlet_temperature": water_outlet,
                        }
                    _LOGGER.debug("VNish %s: final temps result: %s", ip, result)
                    return result if result else None

                _LOGGER.debug("VNish %s: no chains found in miner.chains", ip)

    except Exception as e:
        _LOGGER.debug("VNish %s: failed to fetch temperatures: %s", ip, e)
    return None


async def _fetch_vnish_overclock_limits(ip: str, timeout: int = 10) -> dict | None:
    """Fetch overclock min/max constraints from VNish /api/v1/ui (no auth required).

    Returns dict with keys: min_voltage, max_voltage, min_freq, max_freq (all ints).
    Voltage in mV (e.g. 1400–1700), frequency in MHz (e.g. 50–1000).
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session, session.get(
            f"http://{ip}/api/v1/ui",
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug("VNish %s: /api/v1/ui failed with status %s", ip, resp.status)
                return None
            data = await resp.json(content_type=None)
            oc = data.get("consts", {}).get("overclock", {})
            if not oc:
                return None
            return {
                "min_voltage": int(oc.get("min_voltage", 1400)),
                "max_voltage": int(oc.get("max_voltage", 1700)),
                "default_voltage": int(oc.get("default_voltage", 1530)),
                "min_freq": int(oc.get("min_freq", 50)),
                "max_freq": int(oc.get("max_freq", 1000)),
                "default_freq": int(oc.get("default_freq", 645)),
                "warn_freq": int(oc.get("warn_freq", 670)),
            }
    except Exception as e:
        _LOGGER.debug("VNish %s: failed to fetch /api/v1/ui: %s", ip, e)
    return None


async def _fetch_vnish_overclock_settings(ip: str, password: str = "admin") -> dict | None:
    """Fetch current global overclock settings (volt + freq) from VNish via /api/v1/settings.

    Requires authentication. Returns dict with keys: voltage (mV), freq (MHz).
    """
    import aiohttp

    base_url = f"http://{ip}/api/v1"
    try:
        async with aiohttp.ClientSession() as session:
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

            async with session.get(
                f"{base_url}/settings",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                globals_ = data.get("miner", {}).get("overclock", {}).get("globals", {})
                if not globals_:
                    return None
                return {
                    "voltage": int(globals_.get("volt", 1530)),
                    "freq": int(globals_.get("freq", 645)),
                }
    except Exception as e:
        _LOGGER.debug("VNish %s: failed to fetch overclock settings: %s", ip, e)
    return None


async def _set_vnish_overclock(
    ip: str, freq: int | None = None, voltage: int | None = None, password: str = "admin"
) -> bool:
    """Set global overclock voltage and/or frequency on a VNish miner.

    Reads current settings first, patches only the provided values, then POSTs back.
    Voltage in mV, frequency in MHz.
    """
    import aiohttp

    base_url = f"http://{ip}/api/v1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/unlock",
                json={"pw": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("VNish %s: unlock failed: %s", ip, resp.status)
                    return False
                token = (await resp.json()).get("token")
                if not token:
                    return False

            # Read current full settings
            async with session.get(
                f"{base_url}/settings",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return False
                current = await resp.json(content_type=None)

            # Patch only the globals we want to change
            try:
                globals_ = current["miner"]["overclock"]["globals"]
                if freq is not None:
                    globals_["freq"] = int(freq)
                if voltage is not None:
                    globals_["volt"] = int(voltage)
            except (KeyError, TypeError) as e:
                _LOGGER.debug("VNish %s: could not patch settings: %s", ip, e)
                return False

            # POST back the full settings object
            async with session.post(
                f"{base_url}/settings",
                headers={"Authorization": token},
                json=current,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                success = resp.status == 200
                _LOGGER.debug(
                    "VNish %s: POST /settings status=%s freq=%s volt=%s",
                    ip, resp.status, freq, voltage
                )
                return success
    except Exception as e:
        _LOGGER.debug("VNish %s: failed to set overclock: %s", ip, e)
    return False


async def _set_vnish_throttle(ip: str, percent: int, password: str = "admin") -> bool:
    """Set the mining throttle level on a VNish miner (VNish >= 1.3.3).

    percent is the target power level in percent of full power (e.g. 50 cuts
    hashrate roughly in half without stopping the miner). Endpoint and payload
    match what the VNish web UI itself calls (POST /mining/throttle with
    {"percent": N}); verified live against an S19 Pro Hydro on VNish 1.3.3.
    """
    import aiohttp

    base_url = f"http://{ip}/api/v1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/unlock",
                json={"pw": password},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("VNish %s: unlock failed: %s", ip, resp.status)
                    return False
                token = (await resp.json()).get("token")
                if not token:
                    return False

            async with session.post(
                f"{base_url}/mining/throttle",
                headers={"Authorization": token},
                json={"percent": int(percent)},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                success = resp.status == 200
                _LOGGER.debug(
                    "VNish %s: POST /mining/throttle percent=%s status=%s",
                    ip, percent, resp.status,
                )
                if not success:
                    _LOGGER.warning(
                        "VNish %s: throttle to %s%% failed (HTTP %s)",
                        ip, percent, resp.status,
                    )
                return success
    except Exception as e:
        _LOGGER.debug("VNish %s: failed to set throttle: %s", ip, e)
    return False


def _is_vnish_miner(miner, fw_ver: str = "") -> bool:
    """Check if miner is running VNish firmware."""
    if miner is None:
        return False

    # Check web API type
    if miner.web is not None:
        if type(miner.web).__name__ == "VNishWebAPI":
            return True

    # Check firmware version string for VNish patterns
    fw_ver_lower = str(fw_ver or "").lower()
    if "vnish" in fw_ver_lower:
        return True

    # Check miner class name
    miner_class_name = miner.__class__.__name__.lower()
    if "vnish" in miner_class_name:
        return True

    return False


def _is_bos_miner(miner, fw_ver: str = "") -> bool:
    """Check if miner is running BrainOS (Braiins OS) firmware."""
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
    fw_ver_lower = str(fw_ver or "").lower()
    if any(pattern in fw_ver_lower for pattern in ["braiins", "bos+", "bos-", "-plus"]):
        return True

    # Check if firmware looks like a BrainOS date-based version
    # Pattern: YYYY-MM-DD followed by hash and version
    if re.match(r"\d{4}-\d{2}-\d{2}-\d+-[a-f0-9]+-\d+\.\d+", fw_ver_lower):
        return True

    return False


def _is_bitaxe_miner(miner) -> bool:
    """Check if miner is a BitAxe (ESPMiner-based) device."""
    if miner is None:
        return False
    miner_class_name = miner.__class__.__name__.lower()
    if "bitaxe" in miner_class_name:
        return True
    # Check class hierarchy names
    for cls in type(miner).__mro__:
        if "bitaxe" in cls.__name__.lower():
            return True
    return False


async def _fetch_bitaxe_summary(ip: str, timeout: int = 10) -> dict | None:
    """Fetch best share and found blocks from BitAxe via /api/system/info."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session, session.get(
            f"http://{ip}/api/system/info",
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug("BitAxe %s: system/info failed with status %s", ip, resp.status)
                return None
            data = await resp.json(content_type=None)
            result = {}
            if "bestDiff" in data:
                result["best_share"] = data["bestDiff"]
            if "blockFound" in data:
                result["found_blocks"] = int(data["blockFound"])
            return result if result else None
    except Exception as e:
        _LOGGER.debug("BitAxe %s: failed to fetch system/info: %s", ip, e)
    return None


def _is_hydro_miner(model: str) -> bool:
    """Check if miner is a hydro-cooled (no fans) model."""
    if not model:
        return False
    return "hyd" in model.lower()


async def _bos_rest_login(
    session, ip: str, username: str, password: str
) -> str | None:
    """Authenticate with BOS REST API and return session token.

    BOS REST API uses raw token in Authorization header (no Bearer prefix).
    """
    import aiohttp

    try:
        async with session.post(
            f"http://{ip}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug("BOS REST %s: login failed with status %s", ip, resp.status)
                return None
            data = await resp.json()
            return data.get("token")
    except Exception as e:
        _LOGGER.debug("BOS REST %s: login error: %s", ip, e)
        return None


async def _fetch_bos_rest_stats(
    ip: str, username: str = "root", password: str = "root"
) -> dict | None:
    """Fetch miner stats (best_share, found_blocks) from BOS miner via REST API.

    Uses GET /api/v1/miner/stats.
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            token = await _bos_rest_login(session, ip, username, password)
            if not token:
                return None

            async with session.get(
                f"http://{ip}/api/v1/miner/stats",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("BOS REST %s: miner/stats failed: %s", ip, resp.status)
                    return None
                data = await resp.json()

            miner_stats = data.get("miner_stats", {})
            return {
                "best_share": miner_stats.get("best_share", 0),
                "found_blocks": miner_stats.get("found_blocks", 0),
            }
    except Exception as e:
        _LOGGER.debug("BOS REST %s: stats fetch error: %s", ip, e)
        return None


async def _fetch_bos_rest_hashboards(
    ip: str, username: str = "root", password: str = "root"
) -> dict | None:
    """Fetch hashboard temperatures from BOS miner via REST API.

    Uses GET /api/v1/miner/hw/hashboards.
    Returns dict keyed by 0-based slot index with temperature values.
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            token = await _bos_rest_login(session, ip, username, password)
            if not token:
                return None

            async with session.get(
                f"http://{ip}/api/v1/miner/hw/hashboards",
                headers={"Authorization": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug(
                        "BOS REST %s: miner/hw/hashboards failed: %s", ip, resp.status
                    )
                    return None
                data = await resp.json()

            result = {}
            for board in data.get("hashboards", []):
                board_id = board.get("id", "1")
                try:
                    slot = int(board_id) - 1
                except (ValueError, TypeError):
                    slot = 0

                board_temp = (board.get("board_temp") or {}).get("degree_c")
                chip_temp = (
                    (board.get("highest_chip_temp") or {})
                    .get("temperature", {})
                    .get("degree_c")
                )
                inlet_temp = (board.get("lowest_inlet_temp") or {}).get("degree_c")
                outlet_temp = (board.get("highest_outlet_temp") or {}).get("degree_c")

                # Estimated water circuit temperatures.
                # The BOS API does not expose water inlet/outlet temperatures
                # directly. The BOS web UI reports them but the values are not
                # available in /api/v1/miner/hw/hashboards or any other public
                # endpoint on firmware <=26.04-plus. Empirical comparison
                # against the BOS fleet dashboard on an Antminer S21e Hydro
                # shows the following relationships (per board):
                #   water_outlet ≈ lowest_inlet_temp + 0.85 °C  (±0.2 °C)
                #   water_inlet  ≈ lowest_inlet_temp - 8.60 °C  (±1.0 °C)
                # These are approximations only; actual water temperatures may
                # differ depending on flow rate, ambient and load.
                if inlet_temp is not None:
                    water_outlet_est = round(inlet_temp + 0.85, 1)
                    water_inlet_est = round(inlet_temp - 8.6, 1)
                else:
                    water_outlet_est = None
                    water_inlet_est = None

                stats = board.get("stats") or {}
                hashrate_gh = (
                    stats
                    .get("real_hashrate", {})
                    .get("last_5m", {})
                    .get("gigahash_per_second")
                )
                board_hashrate_th = (
                    round(hashrate_gh / 1000, 2) if hashrate_gh is not None else None
                )
                nominal_gh = (
                    (stats.get("nominal_hashrate") or {})
                    .get("gigahash_per_second")
                )
                board_nominal_hashrate_th = (
                    round(nominal_gh / 1000, 2) if nominal_gh is not None else None
                )

                result[slot] = {
                    "board_temperature": board_temp,
                    "board_temperature_min": inlet_temp,
                    "chip_temperature": chip_temp,
                    "chip_temperature_min": outlet_temp,
                    "inlet_temperature": inlet_temp,
                    "outlet_temperature": outlet_temp,
                    "water_inlet_temperature": water_inlet_est,
                    "water_outlet_temperature": water_outlet_est,
                    "board_hashrate": board_hashrate_th,
                    "board_nominal_hashrate": board_nominal_hashrate_th,
                }

            _LOGGER.debug("BOS REST %s: hashboards result: %s", ip, result)
            return result if result else None
    except Exception as e:
        _LOGGER.debug("BOS REST %s: hashboards fetch error: %s", ip, e)
        return None


async def _fetch_bos_miner_stats(
    ip: str, username: str = "root", password: str = "root"
) -> dict | None:
    """Fetch miner stats (best_share, found_blocks) from BOS miner via gRPC API.

    Uses braiins.bos.v1.MinerService/GetMinerStats on port 50051.
    """
    try:
        import grpc.aio

        # Create async channel
        channel = grpc.aio.insecure_channel(f"{ip}:50051")

        try:
            # Step 1: Login to get auth token
            login_data = _encode_login_request(username, password)

            login_response = await channel.unary_unary(
                "/braiins.bos.v1.AuthenticationService/Login",
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )(login_data)

            token = _parse_login_response(login_response)
            if not token:
                _LOGGER.debug("BOS gRPC: Failed to get auth token for stats")
                return None

            # Step 2: Get miner stats with auth token
            metadata = [("authorization", token)]
            stats_response = await channel.unary_unary(
                "/braiins.bos.v1.MinerService/GetMinerStats",
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )(b"", metadata=metadata)

            _LOGGER.debug(
                f"BOS gRPC stats raw response: {stats_response.hex() if stats_response else 'None'}"
            )
            result = _parse_miner_stats_response(stats_response)
            _LOGGER.debug(f"BOS gRPC stats parsed result: {result}")
            return result

        finally:
            await channel.close()

    except ImportError:
        _LOGGER.debug("grpcio not available for BOS stats")
        return None
    except Exception as e:
        _LOGGER.debug(f"BOS gRPC stats error: {e}")
        return None


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = []
    while value > 127:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _encode_string(field_num: int, value: str) -> bytes:
    """Encode a string field in protobuf format."""
    encoded = value.encode("utf-8")
    tag = (field_num << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(encoded)) + encoded


def _encode_login_request(username: str, password: str) -> bytes:
    """Encode LoginRequest protobuf message."""
    return _encode_string(1, username) + _encode_string(2, password)


def _parse_login_response(data: bytes) -> str | None:
    """Parse LoginResponse protobuf message to extract token."""
    if not data:
        return None

    pos = 0
    while pos < len(data):
        tag_byte = data[pos]
        field_num = tag_byte >> 3
        wire_type = tag_byte & 0x07
        pos += 1

        if wire_type == 2:  # Length-delimited (string)
            length = 0
            shift = 0
            while True:
                b = data[pos]
                pos += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7

            if field_num == 1:  # token field
                return data[pos : pos + length].decode("utf-8")
            pos += length
        elif wire_type == 0:  # Varint
            while data[pos] & 0x80:
                pos += 1
            pos += 1
        else:
            break

    return None


def _parse_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Parse a varint from data at position, return (value, new_pos)."""
    value = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return value, pos


def _parse_miner_stats_response(data: bytes) -> dict | None:
    """Parse GetMinerStatsResponse protobuf message.

    message GetMinerStatsResponse {
        PoolStats pool_stats = 1;
        WorkSolverStats miner_stats = 2;
        MinerPowerStats power_stats = 3;
    }

    Based on bos-plus-api proto, WorkSolverStats contains:
    - found_blocks = 4 (uint32)
    - best_share = 5 (uint64)
    """
    if not data:
        _LOGGER.debug("BOS gRPC: GetMinerStatsResponse is empty")
        return None

    result = {}
    _LOGGER.debug(f"BOS gRPC: parsing GetMinerStatsResponse, len={len(data)}")

    try:
        pos = 0
        while pos < len(data):
            if pos >= len(data):
                break

            tag_byte = data[pos]
            field_num = tag_byte >> 3
            wire_type = tag_byte & 0x07
            pos += 1

            _LOGGER.debug(f"BOS gRPC outer: field={field_num}, wire_type={wire_type}, pos={pos}")

            if wire_type == 2:  # Length-delimited (embedded message)
                length, pos = _parse_varint(data, pos)
                _LOGGER.debug(f"BOS gRPC outer: embedded message field {field_num}, len={length}")
                if field_num == 2:  # miner_stats field (WorkSolverStats)
                    # Parse the embedded WorkSolverStats message
                    inner_data = data[pos : pos + length]
                    inner_result = _parse_miner_stats_inner(inner_data)
                    if inner_result:
                        result.update(inner_result)
                pos += length
            elif wire_type == 0:  # Varint
                _, pos = _parse_varint(data, pos)
            elif wire_type == 1:  # 64-bit
                pos += 8
            elif wire_type == 5:  # 32-bit
                pos += 4
            else:
                _LOGGER.debug(f"BOS gRPC outer: unknown wire_type {wire_type}")
                break

    except Exception as e:
        _LOGGER.debug(f"Error parsing BOS miner stats: {e}")

    return result if result else None


def _parse_miner_stats_inner(data: bytes) -> dict | None:
    """Parse inner MinerStats message to extract best_share and found_blocks.

    Looking for fields by scanning all varint fields.
    best_share is uint64, found_blocks is uint32.
    """
    if not data:
        _LOGGER.debug("BOS gRPC: inner data is empty")
        return None

    # Default values - protobuf doesn't send fields with value 0
    result = {"best_share": 0, "found_blocks": 0}
    pos = 0
    _LOGGER.debug(f"BOS gRPC: parsing inner WorkSolverStats, len={len(data)}")

    try:
        while pos < len(data):
            if pos >= len(data):
                break

            tag_byte = data[pos]
            field_num = tag_byte >> 3
            wire_type = tag_byte & 0x07
            pos += 1

            _LOGGER.debug(f"BOS gRPC inner: field={field_num}, wire_type={wire_type}, pos={pos}")

            if wire_type == 0:  # Varint (uint32, uint64, int32, etc.)
                value, pos = _parse_varint(data, pos)
                _LOGGER.debug(f"BOS gRPC inner: varint field {field_num} = {value}")
                # Based on work.proto WorkSolverStats:
                # found_blocks is field 4 (uint32)
                # best_share is field 5 (uint64)
                if field_num == 4:
                    result["found_blocks"] = value
                elif field_num == 5:
                    result["best_share"] = value
            elif wire_type == 2:  # Length-delimited
                length, pos = _parse_varint(data, pos)
                _LOGGER.debug(f"BOS gRPC inner: skipping embedded message field {field_num}, len={length}")
                pos += length
            elif wire_type == 1:  # 64-bit
                pos += 8
            elif wire_type == 5:  # 32-bit
                pos += 4
            else:
                _LOGGER.debug(f"BOS gRPC inner: unknown wire_type {wire_type}")
                break

    except Exception as e:
        _LOGGER.debug(f"Error parsing MinerStats inner: {e}")

    _LOGGER.debug(f"BOS gRPC inner: result = {result}")
    return result  # Always return dict with defaults


class MinerCoordinator(DataUpdateCoordinator):
    """Class to manage fetching update data from the Miner."""

    miner: "pyasic.AnyMiner" = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize MinerCoordinator object."""
        self.miner = None
        self._failure_count = 0
        # True while running on cached-profile data because the miner was
        # unreachable during setup; cleared on the first successful update.
        self._primed_offline = False
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=60),
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
        # Never detected (yet) -> unavailable. After detection the miner object
        # is cached (detect-once), so reachability has to come from the update
        # results instead: tolerate a short failure streak, then report
        # unavailable on sustained failures (e.g. miner powered off at the
        # wall) rather than keeping entities alive with frozen data forever.
        if self.miner is None:
            return False
        return self._failure_count <= AVAILABILITY_FAILURE_THRESHOLD

    def _keep_last_or_fail(self, message: str, err: Exception | None = None):
        """Handle a failed poll: absorb short hiccups, raise on streaks.

        The first TRANSIENT_FAILURE_GRACE consecutive failures return the
        last-known-good data (DEBUG only), so one flaky poll doesn't produce
        an ERROR log line and a state flap. Anything longer raises
        UpdateFailed and goes through the standard coordinator handling.
        """
        self._failure_count += 1
        if self.data and self._failure_count <= TRANSIENT_FAILURE_GRACE:
            _LOGGER.debug(
                "Update for %s failed (consecutive failure %d, within grace), "
                "keeping last data: %s",
                self.name,
                self._failure_count,
                message,
            )
            return self.data
        if err is not None:
            raise UpdateFailed(message) from err
        raise UpdateFailed(message)

    @property
    def cached_profile(self) -> dict:
        """Device profile captured on the last successful update (may be {})."""
        return self.config_entry.data.get(CONF_CACHED_PROFILE) or {}

    def prime_from_cached_profile(self) -> None:
        """Populate coordinator data from the cached device profile.

        Used when the miner cannot be detected during setup (typically
        powered off to save energy): entities are created from the cached
        identity and report unavailable (self.miner is None) until the miner
        returns; detection is retried on every poll via get_miner().
        """
        profile = self.cached_profile
        data = copy.deepcopy(DEFAULT_DATA)
        data["hostname"] = profile.get("hostname")
        data["mac"] = profile.get("mac")
        data["make"] = profile.get("make")
        data["model"] = profile.get("model")
        data["fw_ver"] = profile.get("fw_ver")
        data["ip"] = self.config_entry.data.get(CONF_IP)
        data["power_limit_range"] = {
            "min": self.config_entry.data.get(CONF_MIN_POWER, 15),
            "max": self.config_entry.data.get(CONF_MAX_POWER, 10000),
        }
        self.data = data
        self._primed_offline = True

    def _persist_device_profile(self, data) -> None:
        """Store the device profile in the config entry (only when changed)."""
        try:
            miner = self.miner
            fw_ver = str(data.get("fw_ver") or "")
            fw_lower = fw_ver.lower()
            model_lower = str(data.get("model") or "").lower()
            has_modern_vnish_api = (
                miner is not None
                and miner.web is not None
                and type(miner.web).__name__ == "VNishWebAPI"
            )
            profile = {
                "hostname": data.get("hostname"),
                "mac": data.get("mac"),
                "make": data.get("make"),
                "model": data.get("model"),
                "fw_ver": data.get("fw_ver"),
                "is_vnish": _is_vnish_miner(miner, fw_ver),
                "is_bos": _is_bos_miner(miner, fw_ver),
                "is_avalon": _is_avalon_nano_miner(miner),
                "is_bitaxe": _is_bitaxe_miner(miner),
                # Mirrors switch._is_vnish_legacy_miner (CGI-bin based VNish 3.x)
                "is_vnish_legacy": (
                    not has_modern_vnish_api
                    and (
                        "vnish 3" in fw_lower
                        or "vnish-3" in fw_lower
                        or "s9d" in model_lower
                        or "s9 dual" in model_lower
                    )
                ),
                "expected_hashboards": getattr(miner, "expected_hashboards", None),
                "expected_fans": getattr(miner, "expected_fans", None),
                "fan_count": len(data.get("fan_sensors") or {}),
                "supports_shutdown": bool(getattr(miner, "supports_shutdown", False)),
                "supports_autotuning": bool(
                    getattr(miner, "supports_autotuning", False)
                ),
                # VNish >= 1.3.3 reports a throttle level (vnish_throttle is
                # populated by the throttle feature branch; None/absent on
                # older firmware) - lets the throttle entity be re-created
                # after an offline setup.
                "has_throttle": data.get("vnish_throttle") is not None,
            }
            if profile != self.config_entry.data.get(CONF_CACHED_PROFILE):
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_CACHED_PROFILE: profile},
                )
        except Exception as err:  # profile caching must never break an update
            _LOGGER.debug("Could not persist device profile: %s", err)

    async def get_miner(self):
        """Get a valid Miner instance."""
        import pyasic  # lazy import to avoid blocking event loop

        # detect-once: reuse a previously detected miner instead of re-running the
        # slow, under-load-flaky auto-detection on every poll.
        if self.miner is not None:
            return self.miner

        miner_ip = self.config_entry.data[CONF_IP]
        # Hard timeout: pyasic auto-detection has no internal timeout and can hang
        # indefinitely on a flaky/unreachable miner, blocking setup and the loop.
        # See MINER_DETECTION_TIMEOUT in const.py for why this isn't tiny.
        try:
            miner = await asyncio.wait_for(
                pyasic.get_miner(miner_ip), timeout=MINER_DETECTION_TIMEOUT
            )
        except (TimeoutError, asyncio.TimeoutError):
            _LOGGER.warning("get_miner timed out for %s - treating as offline", miner_ip)
            return None
        if miner is None:
            return None

        if miner.api is not None and miner.api.pwd is not None:
            miner.api.pwd = self.config_entry.data.get(CONF_RPC_PASSWORD, "")
        if miner.web is not None:
            miner.web.username = self.config_entry.data.get(CONF_WEB_USERNAME, "")
            miner.web.pwd = self.config_entry.data.get(CONF_WEB_PASSWORD, "")
        if miner.ssh is not None:
            miner.ssh.username = self.config_entry.data.get(CONF_SSH_USERNAME, "")
            miner.ssh.pwd = self.config_entry.data.get(CONF_SSH_PASSWORD, "")

        # Only cache a *complete* detection. Under load pyasic may return a generic
        # result (model unset) that yields zeroed data; don't freeze on it - re-detect
        # next poll until a full detection succeeds.
        if getattr(miner, "model", None):
            self.miner = miner
        return miner

    async def _async_update_data(self):
        """Fetch sensors from miners."""
        import pyasic  # lazy import to avoid blocking event loop

        miner = await self.get_miner()

        if miner is None:
            if self._primed_offline:
                # Set up from the cached profile while the miner is powered
                # off: this state is expected, so stay quiet (no ERROR per
                # poll) - entities already report unavailable via the
                # available property (self.miner is None). Detection is
                # retried by get_miner() on every poll.
                _LOGGER.debug(
                    "%s: miner still offline, waiting for it to return",
                    self.name,
                )
                return self.data

            # Keep last-known-good data on failure instead of returning zeroed
            # DEFAULT_DATA (which made sensors flap to 0 on transient hiccups).
            return self._keep_last_or_fail("Miner offline")

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
                    # Keep last-known-good data on transient failure (no fake 0).
                    return self._keep_last_or_fail(
                        f"Error fetching miner data: {retry_err}", retry_err
                    )
            else:
                # Keep last-known-good data on transient failure (no fake 0).
                return self._keep_last_or_fail(
                    f"Error fetching miner data: {err}", err
                )

        _LOGGER.debug(f"Got data: {miner_data}")

        # Success: reset the failure count and leave primed-offline mode
        self._failure_count = 0
        self._primed_offline = False

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
                    "board_temperature_min": None,  # VNish only
                    "chip_temperature": board.chip_temp,
                    "chip_temperature_min": None,  # VNish only
                    "inlet_temperature": None,  # BOS only
                    "outlet_temperature": None,  # BOS only
                    "water_inlet_temperature": None,  # BOS only (estimated)
                    "water_outlet_temperature": None,  # BOS only (estimated)
                    "board_hashrate": normalize_hashrate_to_th(board.hashrate),
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
            "vnish_throttle": None,
            "vnish_miner_state": None,
            "vnish_voltage": None,
            "vnish_freq": None,
            "vnish_min_voltage": None,
            "vnish_max_voltage": None,
            "vnish_min_freq": None,
            "vnish_max_freq": None,
            "bos_best_share": None,
            "bos_found_blocks": None,
            "bitaxe_best_share": None,
            "bitaxe_found_blocks": None,
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

        # Fetch VNish data for VNish firmware miners
        if _is_vnish_miner(self.miner, miner_data.fw_ver):
            web_password = self.config_entry.data.get(CONF_WEB_PASSWORD, "admin")

            # Fetch VNish preset
            vnish_preset = await _fetch_vnish_preset(self.miner.ip, web_password)
            if vnish_preset:
                data["vnish_preset"] = vnish_preset

            # Fetch VNish summary data (Best Share, Found Blocks)
            vnish_summary = await _fetch_vnish_summary(self.miner.ip, web_password)
            if vnish_summary:
                data["vnish_best_share"] = vnish_summary.get("best_share")
                data["vnish_found_blocks"] = vnish_summary.get("found_blocks")
                data["vnish_throttle"] = vnish_summary.get("throttled")
                data["vnish_miner_state"] = vnish_summary.get("miner_state")

            # Fetch VNish overclock limits (no auth required)
            vnish_limits = await _fetch_vnish_overclock_limits(self.miner.ip)
            if vnish_limits:
                data["vnish_min_voltage"] = vnish_limits["min_voltage"]
                data["vnish_max_voltage"] = vnish_limits["max_voltage"]
                data["vnish_min_freq"] = vnish_limits["min_freq"]
                data["vnish_max_freq"] = vnish_limits["max_freq"]

            # Fetch current overclock settings (volt + freq)
            vnish_oc = await _fetch_vnish_overclock_settings(self.miner.ip, web_password)
            if vnish_oc:
                data["vnish_voltage"] = vnish_oc["voltage"]
                data["vnish_freq"] = vnish_oc["freq"]

            # Always fetch VNish temperatures directly (bypass pyasic completely)
            vnish_temps = await _fetch_vnish_temperatures(
                self.miner.ip, web_password
            )
            if vnish_temps:
                _LOGGER.debug(
                    "VNish %s: replacing pyasic temps with VNish API data",
                    self.miner.ip,
                )
                # Completely overwrite board_sensors temperatures with VNish API data
                for slot, temps in vnish_temps.items():
                    board_temp = temps.get("board_temperature", 0)
                    board_temp_min = temps.get("board_temperature_min", 0)
                    chip_temp = temps.get("chip_temperature", 0)
                    chip_temp_min = temps.get("chip_temperature_min", 0)
                    water_inlet = temps.get("water_inlet_temperature")
                    water_outlet = temps.get("water_outlet_temperature")
                    if slot in data["board_sensors"]:
                        # Preserve hashrate from pyasic, replace temps from VNish API
                        data["board_sensors"][slot]["board_temperature"] = board_temp
                        data["board_sensors"][slot]["board_temperature_min"] = board_temp_min
                        data["board_sensors"][slot]["chip_temperature"] = chip_temp
                        data["board_sensors"][slot]["chip_temperature_min"] = chip_temp_min
                        data["board_sensors"][slot]["water_inlet_temperature"] = water_inlet
                        data["board_sensors"][slot]["water_outlet_temperature"] = water_outlet
                    else:
                        # Create new board entry with VNish temps
                        data["board_sensors"][slot] = {
                            "board_temperature": board_temp,
                            "board_temperature_min": board_temp_min,
                            "chip_temperature": chip_temp,
                            "chip_temperature_min": chip_temp_min,
                            "water_inlet_temperature": water_inlet,
                            "water_outlet_temperature": water_outlet,
                            "board_hashrate": 0,
                        }
                _LOGGER.debug(
                    "VNish %s: final board_sensors: %s",
                    self.miner.ip,
                    data["board_sensors"],
                )
            else:
                # The VNish REST endpoint is the only temperature source for
                # these miners (pyasic does not deliver VNish board temps -
                # that's why this fetch exists). On a transient fetch failure,
                # keep the last known temperatures instead of pushing the
                # sensors to unknown for one poll cycle, which also spams any
                # downstream group/template sensors.
                prev_boards = (self.data or {}).get("board_sensors") or {}
                temp_keys = (
                    "board_temperature",
                    "board_temperature_min",
                    "chip_temperature",
                    "chip_temperature_min",
                    "water_inlet_temperature",
                    "water_outlet_temperature",
                )
                restored = 0
                for slot, prev_vals in prev_boards.items():
                    cur = data["board_sensors"].get(slot)
                    if cur is None:
                        continue
                    for key in temp_keys:
                        # 0 is the VNish placeholder for "no reading", not a
                        # plausible operating temperature.
                        if not cur.get(key) and prev_vals.get(key):
                            cur[key] = prev_vals[key]
                            restored += 1
                if restored:
                    _LOGGER.info(
                        "VNish %s: temperature fetch failed, keeping %d last "
                        "known temperature value(s) until the next poll",
                        self.miner.ip,
                        restored,
                    )
                else:
                    _LOGGER.warning(
                        "VNish %s: temperature fetch failed and no previous "
                        "temperatures to fall back on",
                        self.miner.ip,
                    )

        # Fetch BOS miner stats and hashboard temps via REST API
        if _is_bos_miner(self.miner, miner_data.fw_ver):
            web_username = self.config_entry.data.get(CONF_WEB_USERNAME, "root")
            web_password = self.config_entry.data.get(CONF_WEB_PASSWORD, "root")

            bos_stats = await _fetch_bos_rest_stats(
                self.miner.ip, web_username, web_password
            )
            if bos_stats:
                data["bos_best_share"] = bos_stats.get("best_share")
                data["bos_found_blocks"] = bos_stats.get("found_blocks")

            bos_hashboards = await _fetch_bos_rest_hashboards(
                self.miner.ip, web_username, web_password
            )
            if bos_hashboards:
                _LOGGER.debug(
                    "BOS REST %s: replacing pyasic board temps with REST API data",
                    self.miner.ip,
                )
                for slot, temps in bos_hashboards.items():
                    if slot in data["board_sensors"]:
                        data["board_sensors"][slot].update(temps)
                    else:
                        data["board_sensors"][slot] = temps

                # Use sum of nominal hashrates from REST API as ideal_hashrate
                total_nominal = sum(
                    v.get("board_nominal_hashrate") or 0 for v in bos_hashboards.values()
                )
                if total_nominal:
                    data["miner_sensors"]["ideal_hashrate"] = round(total_nominal, 2)

            # Hydro-cooled miners have no fans — clear any fan sensors from pyasic
            model = data.get("model") or miner_data.model or ""
            if _is_hydro_miner(model):
                data["fan_sensors"] = {}
                _LOGGER.debug(
                    "BOS REST %s: hydro miner detected (%s), suppressing fan sensors",
                    self.miner.ip,
                    model,
                )

        # Fetch BitAxe summary data (Best Share, Found Blocks)
        if _is_bitaxe_miner(self.miner):
            bitaxe_summary = await _fetch_bitaxe_summary(self.miner.ip)
            if bitaxe_summary:
                data["bitaxe_best_share"] = bitaxe_summary.get("best_share")
                data["bitaxe_found_blocks"] = bitaxe_summary.get("found_blocks")

        # Cache identity/capabilities so the next setup can succeed while the
        # miner is powered off (see prime_from_cached_profile).
        self._persist_device_profile(data)

        return data
