"""The Miner integration."""
from __future__ import annotations

import sys
import os

# Inject bundled dependencies (betterproto, pyasic, etc.) into path
# These are packages not provided by HA or requiring specific pre-release versions
_integration_path = os.path.dirname(os.path.abspath(__file__))
_deps_path = os.path.join(_integration_path, "deps")

if os.path.isdir(_deps_path) and _deps_path not in sys.path:
    sys.path.insert(0, _deps_path)  # Insert first to get pre-release betterproto

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_IP
from .const import DOMAIN
from .const import PYASIC_VERSION

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.LIGHT,
    Platform.BUTTON,
]


def _ensure_pyasic():
    """Ensure pyasic is available (bundled version)."""
    import importlib
    
    # Apply Python 3.14 compatibility patch BEFORE importing pyasic
    from .patch import apply_pydantic_property_patch
    apply_pydantic_property_patch()
    
    # Import bundled pyasic (path already injected at module load)
    import pyasic
    
    # Verify the module loaded correctly
    if not hasattr(pyasic, 'get_miner'):
        raise ImportError("pyasic module incomplete")
    
    # Apply patches after pyasic is loaded
    from .patch import apply_whatsminer_power_limit_patch
    from .patch import apply_avalonminer_web_patch
    from .patch import apply_vnish_get_config_patch
    apply_whatsminer_power_limit_patch()
    apply_avalonminer_web_patch()
    apply_vnish_get_config_patch()
    
    return pyasic


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Miner from a config entry."""
    # Import pyasic in executor to avoid blocking the event loop
    try:
        pyasic = await hass.async_add_executor_job(_ensure_pyasic)
    except (ImportError, KeyError) as err:
        # Clear broken modules so next retry has fresh start
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith('pyasic'):
                del sys.modules[mod_name]
        raise ConfigEntryNotReady(f"pyasic import failed: {err}") from err

    # Import coordinator and services AFTER pyasic is installed
    from .coordinator import MinerCoordinator
    from .services import async_setup_services

    miner_ip = config_entry.data[CONF_IP]
    miner = await pyasic.get_miner(miner_ip)

    if miner is None:
        raise ConfigEntryNotReady("Miner could not be found.")

    m_coordinator = MinerCoordinator(hass, config_entry)
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = m_coordinator

    await m_coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
