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

# Avalon control mode options
AVALON_MODE_SIMPLE = "simple"  # Native pyasic only
AVALON_MODE_FULL = "full"      # Full CGMiner API control (workmode, LED, mining switch)

SERVICE_REBOOT = "reboot"
SERVICE_RESTART_BACKEND = "restart_backend"
SERVICE_SET_WORK_MODE = "set_work_mode"

# pyasic 0.78.8 - works with Avalon Nano 3s
# Note: Whatsminer users may need to manually enable API via WhatsMinerTool
PYASIC_VERSION = "0.78.8"

TERA_HASH_PER_SECOND = "TH/s"
JOULES_PER_TERA_HASH = "J/TH"
