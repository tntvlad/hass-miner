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

SERVICE_REBOOT = "reboot"
SERVICE_RESTART_BACKEND = "restart_backend"
SERVICE_SET_WORK_MODE = "set_work_mode"

# pyasic 0.75.0 is used because:
# - 0.78.x requires pydantic>=2.12.5 but HA has 2.12.2
# - 0.75.0 has the open_api() fallback that was removed in 0.78.x
PYASIC_VERSION = "0.75.0"

TERA_HASH_PER_SECOND = "TH/s"
JOULES_PER_TERA_HASH = "J/TH"


PYASIC_VERSION = "0.78.9"
