"""Constants for the Miner integration."""

DOMAIN = "miner"

CONF_IP = "ip"
CONF_TITLE = "title"
CONF_SSH_PASSWORD = "ssh_password"
CONF_SSH_USERNAME = "ssh_username"
CONF_RPC_PASSWORD = "rpc_password"
CONF_WEB_PASSWORD = "web_password"
CONF_WEB_USERNAME = "web_username"
CONF_MIN_POWER = "min_power"
CONF_MAX_POWER = "max_power"
CONF_AVALON_CONTROL_MODE = "avalon_control_mode"

# Config-entry data key for the device profile captured on the last successful
# update (identity, capabilities, firmware-type flags). Lets the integration
# set up while the miner is powered off (e.g. for energy saving) instead of
# failing with ConfigEntryNotReady and showing as broken until it returns.
CONF_CACHED_PROFILE = "cached_device_profile"

# Avalon control mode options
AVALON_MODE_SIMPLE = "simple"  # Native pyasic only
AVALON_MODE_FULL = "full"  # Full CGMiner API control (workmode, LED, mining switch)

SERVICE_REBOOT = "reboot"
SERVICE_RESTART_BACKEND = "restart_backend"
SERVICE_SET_WORK_MODE = "set_work_mode"

# pyasic 0.78.0 - works with Avalon Nano 3s and pydantic>=2.11.0 (compatible with HA)
# Note: Whatsminer users may need to manually enable API via WhatsMinerTool
# Python 3.14 requires pydantic patch (applied in patch.py)
PYASIC_VERSION = "0.78.12"

# Hard timeout (seconds) for pyasic auto-detection (get_miner). pyasic has no
# internal timeout and can hang indefinitely on a flaky/unreachable miner.
# A full BOS+ detection legitimately takes 24-30s under load, so this must stay
# comfortably above that - too small a value spuriously times out valid miners
# during setup, leaving the config entry stuck in setup_retry.
MINER_DETECTION_TIMEOUT = 45

TERA_HASH_PER_SECOND = "TH/s"
JOULES_PER_TERA_HASH = "J/TH"
