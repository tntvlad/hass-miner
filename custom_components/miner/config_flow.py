"""Config flow for Miner."""

import asyncio
import contextlib
import ipaddress
import json
import logging
import time
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AVALON_MODE_FULL,
    AVALON_MODE_SIMPLE,
    CONF_AVALON_CONTROL_MODE,
    CONF_IP,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_RESCAN,
    CONF_RPC_PASSWORD,
    CONF_SCAN_MINER,
    CONF_SCAN_NETWORK,
    CONF_SSH_PASSWORD,
    CONF_SSH_USERNAME,
    CONF_TITLE,
    CONF_WEB_PASSWORD,
    CONF_WEB_USERNAME,
    DOMAIN,
    MAX_SCAN_CONCURRENCY,
    MAX_SCAN_HOSTS,
    PYASIC_VERSION,
    SCAN_HTTP_PORT,
    SCAN_HTTP_TIMEOUT,
    SCAN_IDENTIFY_TIMEOUT,
    SCAN_PING_TIMEOUT,
    SCAN_TIMEOUT,
)

# Lazy import - will be populated when needed
pyasic = None
MinerNetwork = None
MinerMake = None


def _ensure_pyasic():
    """Ensure pyasic is installed and imported."""
    global pyasic, MinerNetwork, MinerMake
    if pyasic is not None:
        return

    # Apply Python 3.14 compatibility patch BEFORE importing pyasic
    from .patch import apply_pydantic_property_patch

    apply_pydantic_property_patch()

    try:
        import pyasic as _pyasic

        if version("pyasic") != PYASIC_VERSION:
            raise ImportError("Version mismatch")
    except (ImportError, Exception):
        from .patch import install_package

        install_package(f"pyasic=={PYASIC_VERSION}", no_deps=True)
        import pyasic as _pyasic

    pyasic = _pyasic
    from pyasic import MinerNetwork as _MinerNetwork

    MinerNetwork = _MinerNetwork
    from pyasic.device.makes import MinerMake as _MinerMake

    MinerMake = _MinerMake


_LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _integration_version() -> str:
    """Read the integration version from manifest.json for scan diagnostics.

    Stamped into scan log lines so a submitted log unambiguously shows which
    build produced them (HACS updates only take effect after an HA restart).
    """
    try:
        with open(Path(__file__).parent / "manifest.json") as f:
            return str(json.load(f).get("version", "?"))
    except Exception:
        return "?"

# Ranges that never contain user miners: unspecified, loopback, link-local,
# CGNAT (Tailscale/VPN), multicast/reserved. Scanning them wastes time and
# on large VPN ranges can exhaust memory.
_SKIP_RANGES = [
    ipaddress.ip_network(range_str)
    for range_str in (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "224.0.0.0/3",
    )
]


def _validate_custom_cidr(value) -> tuple[ipaddress.IPv4Network | None, str | None]:
    """Validate a user-entered CIDR for scanning.

    Returns (network, error_base). A blank value means "no custom range"
    and validates to (None, None).
    """
    if value is None or not str(value).strip():
        return None, None
    try:
        net = ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError:
        return None, "invalid_cidr"
    if not isinstance(net, ipaddress.IPv4Network):
        return None, "invalid_cidr"
    if net.num_addresses > MAX_SCAN_HOSTS:
        return None, "cidr_too_large"
    if any(net.overlaps(skip) for skip in _SKIP_RANGES):
        return None, "invalid_cidr"
    return net, None


def _usable_subnet(net: ipaddress.IPv4Network) -> bool:
    """Return whether a network is worth scanning."""
    if not isinstance(net, ipaddress.IPv4Network):
        return False
    if net.num_addresses > MAX_SCAN_HOSTS:
        _LOGGER.info(
            "Skipping oversized subnet %s (%d addresses > %d)",
            net,
            net.num_addresses,
            MAX_SCAN_HOSTS,
        )
        return False
    if any(net.overlaps(skip) for skip in _SKIP_RANGES):
        _LOGGER.info("Skipping internal subnet %s", net)
        return False
    return True


async def _async_candidate_subnets(
    hass: HomeAssistant, custom_net: ipaddress.IPv4Network | None = None
) -> list[ipaddress.IPv4Network]:
    """Build the list of networks worth scanning.

    Sources, in order of preference (first match wins on overlap):
      1. an explicitly user-entered CIDR
      2. /24s around already-configured miner IPs - on Home Assistant OS the
         HA container only sees its internal bridge, so existing miner IPs are
         the only reliable hint where the LAN actually is
      3. adapter subnets (Container/venv installs where HA sits on the LAN)
    """
    candidates: list[ipaddress.IPv4Network] = []

    def _add(net: ipaddress.IPv4Network | None) -> None:
        if net is None or not _usable_subnet(net):
            return
        # Skip exact duplicates and subnets contained in one we already have.
        if any(net.subnet_of(existing) or existing.subnet_of(net) for existing in candidates):
            return
        candidates.append(net)

    if custom_net is not None:
        _add(custom_net)

    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN or entry.source == config_entries.SOURCE_IGNORE:
            continue
        try:
            addr = ipaddress.ip_address(str(entry.data.get(CONF_IP, "")))
        except ValueError:
            continue
        if addr.version != 4:
            continue
        _add(ipaddress.ip_network(f"{addr}/24", strict=False))

    try:
        adapters = await network.async_get_adapters(hass)
    except Exception:
        _LOGGER.warning("Could not enumerate network adapters", exc_info=True)
        adapters = []
    for adapter in adapters:
        for ip_info in adapter.get("ipv4") or []:
            local_ip = ip_info.get("address")
            prefix = ip_info.get("network_prefix")
            if not local_ip or prefix in (None, ""):
                continue
            try:
                net = ipaddress.ip_network(f"{local_ip}/{prefix}", strict=False)
            except ValueError:
                # Malformed adapter data must never kill discovery.
                _LOGGER.warning(
                    "Skipping unusable adapter address %s/%s", local_ip, prefix
                )
                continue
            _add(net)

    _LOGGER.info(
        "Miner discovery will scan: %s", ", ".join(str(net) for net in candidates)
    )
    return candidates


async def _async_tcp_alive(host) -> bool:
    """Return whether anything accepts a TCP connection on the fallback port.

    Unlike pyasic's probe this tolerates an abrupt close: esp-miner devices
    (BitAxe/NerdMiner families) accept the connection and reset it because no
    data follows, which pyasic misclassifies as "refused" - without this
    second chance those miners are never discovered even though they serve
    their API on port 80.
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(str(host), SCAN_HTTP_PORT),
            timeout=SCAN_HTTP_TIMEOUT,
        )
    except Exception:
        return False
        writer.close()
        # A reset here still proves a listener existed - ignore it.
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return True


async def _async_scan_for_miners(
    hass: HomeAssistant, custom_net: ipaddress.IPv4Network | None = None
) -> list:
    """Scan candidate networks for miners.

    Returns a list of detected pyasic miner objects, sorted by IP and
    deduplicated across networks. Hosts are probed through our own semaphore
    (pyasic skips its built-in one by default) and every probe result is
    isolated so a single misbehaving host cannot abort its subnet scan.
    """
    await hass.async_add_executor_job(_ensure_pyasic)

    subnets = await _async_candidate_subnets(hass, custom_net)
    if not subnets:
        return []

    # Short ping timeout while sweeping dead addresses; restored afterwards.
    old_ping_timeout = pyasic.settings.get("network_ping_timeout", 3)
    pyasic.settings.update("network_ping_timeout", SCAN_PING_TIMEOUT)

    probe_semaphore = asyncio.Semaphore(MAX_SCAN_CONCURRENCY)
    scan_started = time.monotonic()
    _LOGGER.info(
        "Network scan starting (integration %s)", _integration_version()
    )

    # Counters for the per-subnet log line - they make the port-80 recheck
    # visible in submitted logs (alive-but-unidentified hosts point at
    # unsupported esp-miner firmware).
    stats = {"rechecked": 0, "identified": 0}

    # IPs of already-configured miners: their probe outcome is logged in
    # detail, which makes submitted logs decisive when a known-live miner
    # (e.g. a BitAxe the coordinator polls fine) is not rediscovered.
    watched_ips = set()
    for entry in hass.config_entries.async_entries():
        if entry.domain != DOMAIN or entry.source == config_entries.SOURCE_IGNORE:
            continue
        ip_value = str(entry.data.get(CONF_IP, "")).strip()
        if ip_value:
            watched_ips.add(ip_value)

    async def _probe_host(miner_net_, host):
        host_str = str(host)
        watched = host_str in watched_ips
        async with probe_semaphore:
            pyasic_result = "miner"
            try:
                miner = await miner_net_.ping_and_get_miner(host)
                if miner is not None:
                    return miner
                pyasic_result = "none"
            except Exception as err:  # noqa: BLE001 - probe must never abort the sweep
                pyasic_result = f"error: {type(err).__name__}"
            # pyasic found nothing - recheck the HTTP port ourselves. This
            # union signal recovers esp-miner devices (BitAxe/NerdMiner)
            # whose abrupt close pyasic misclassifies as "refused".
            alive = await _async_tcp_alive(host)
            if watched:
                _LOGGER.info(
                    "Probe detail for configured %s: pyasic=%s, tcp80=%s",
                    host_str,
                    pyasic_result,
                    "open" if alive else "closed",
                )
            if not alive:
                return None
            stats["rechecked"] += 1
            try:
                miner = await asyncio.wait_for(
                    pyasic.get_miner(str(host)), timeout=SCAN_IDENTIFY_TIMEOUT
                )
            except Exception:
                _LOGGER.debug(
                    "Could not identify %s despite an open port", host, exc_info=True
                )
                return None
            if miner is not None:
                stats["identified"] += 1
            return miner

    miners = []
    seen_ips = set()
    try:
        for subnet in subnets:
            try:
                miner_net = MinerNetwork(list(subnet.hosts()))
                results = await asyncio.gather(
                    *(_probe_host(miner_net, host) for host in miner_net.hosts),
                    return_exceptions=True,
                )
            except Exception:
                _LOGGER.warning("Scanning %s failed", subnet, exc_info=True)
                continue
            probe_errors = [r for r in results if isinstance(r, BaseException)]
            found = [
                r for r in results if r is not None and not isinstance(r, BaseException)
            ]
            if probe_errors:
                _LOGGER.warning(
                    "Scanning %s: %d of %d host probe(s) failed",
                    subnet,
                    len(probe_errors),
                    len(results),
                )
            new_miners = [m for m in found if str(m.ip) not in seen_ips]
            seen_ips.update(str(m.ip) for m in new_miners)
            miners.extend(new_miners)
            _LOGGER.info(
                "Scanned %s: found %d miner(s) (port-80 recheck: %d alive, %d identified)",
                subnet,
                len(new_miners),
                stats["rechecked"],
                stats["identified"],
            )
    finally:
        pyasic.settings.update("network_ping_timeout", old_ping_timeout)

    _LOGGER.info(
        "Network scan finished in %.1fs: %d miner(s) across %d subnet(s)",
        time.monotonic() - scan_started,
        len(miners),
        len(subnets),
    )
    for miner in miners:
        _LOGGER.info(
            "Discovered miner: %s (%s)",
            getattr(miner, "model", "?"),
            getattr(miner, "ip", "?"),
        )

    miners.sort()
    return miners


async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""
    return len(await _async_scan_for_miners(hass)) > 0


async def validate_ip_input(hass: HomeAssistant, data: dict[str, str]):
    """Validate the user input allows us to connect."""
    await hass.async_add_executor_job(_ensure_pyasic)
    miner_ip = data.get(CONF_IP)

    miner = await pyasic.get_miner(miner_ip)
    if miner is None:
        return {"base": "Unable to connect to Miner, is IP correct?"}, None

    return {}, miner


def _is_avalon_miner(miner) -> bool:
    """Check if miner is an Avalon miner."""
    if miner is None:
        return False

    miner_class_name = miner.__class__.__name__.lower()
    make = str(getattr(miner, "make", "") or "").lower()
    model = str(getattr(miner, "model", "") or "").lower()

    return "avalon" in miner_class_name or "avalon" in make or "avalon" in model


class MinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Miner."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._data = {}
        self._miner = None
        self._discovered = None
        self._scan_task = None
        self._scan_done = False
        self._custom_net = None

    async def async_step_user(self, user_input=None):
        """Get miner IP and check if it is available.

        An empty IP address triggers a network scan instead, letting the
        user pick a miner from the discovered list.
        """
        if user_input is None:
            user_input = {}

        schema = vol.Schema(
            {
                vol.Optional(CONF_IP, default=user_input.get(CONF_IP, "")): str,
                vol.Optional(CONF_MIN_POWER, default=15): vol.All(
                    vol.Coerce(int), vol.Range(min=15, max=10000)
                ),
                vol.Optional(CONF_MAX_POWER, default=10000): vol.All(
                    vol.Coerce(int), vol.Range(min=15, max=10000)
                ),
            }
        )

        if not user_input:
            return self.async_show_form(step_id="user", data_schema=schema)

        self._data.update(user_input)

        entered_value = user_input.get(CONF_IP, "").strip()

        if not entered_value:
            # No IP entered - scan the network for miners.
            self._custom_net = None
            self._scan_done = False
            return await self.async_step_scan()

        if "/" in entered_value:
            # A CIDR range in the IP field means "scan this range" - saves a
            # round-trip through the empty-IP flow for users who know their
            # subnet. Bare IPs fall through to the connect check.
            custom_net, cidr_error = _validate_custom_cidr(entered_value)
            if cidr_error:
                return self.async_show_form(
                    step_id="user", data_schema=schema, errors={"base": cidr_error}
                )
            self._custom_net = custom_net
            self._scan_done = False
            return await self.async_step_scan()

        errors, miner = await validate_ip_input(self.hass, user_input)

        if errors:
            return self.async_show_form(
                step_id="user", data_schema=schema, errors=errors
            )

        self._miner = miner
        self._data.update(user_input)
        return await self.async_step_login()

    @staticmethod
    def _miner_label(miner) -> str:
        """Build a display label for a discovered miner."""
        model = str(getattr(miner, "model", "") or "Unknown")
        ip = str(getattr(miner, "ip", "") or "?")
        return f"{model} ({ip})"

    def _log_scan_exception(self, task: asyncio.Task) -> None:
        """Log exceptions from the background scan task if nobody awaited it."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.warning("Background miner network scan failed: %s", exc)

    async def _start_scan(self):
        """Launch the network scan as a background task and show progress."""
        self._discovered = None
        self._scan_done = False
        custom_net = self._custom_net

        async def _scan_with_timeout():
            return await asyncio.wait_for(
                _async_scan_for_miners(self.hass, custom_net), timeout=SCAN_TIMEOUT
            )

        self._scan_task = self.hass.async_create_task(_scan_with_timeout())
        self._scan_task.add_done_callback(self._log_scan_exception)
        return self.async_show_progress(
            step_id="scan",
            progress_action="scan_network",
            # Required by HA: lets the flow manager track and cancel the task
            # if the user dismisses the dialog mid-scan. Without it the scan
            # can be orphaned and never resurfaces.
            progress_task=self._scan_task,
        )

    async def async_step_scan(self, user_input=None):
        """Show a progress screen while the scan runs, then move to results.

        While the progress screen is up, the frontend polls this step; once
        the background task has finished the poll moves the flow to
        ``scan_result``.
        """
        # Stray polls after completion must not restart the scan.
        if self._scan_done and self._scan_task is None:
            return self.async_show_progress_done(next_step_id="scan_result")

        if self._scan_task is None:
            return await self._start_scan()

        try:
            self._discovered = await self._scan_task
        except (TimeoutError, asyncio.TimeoutError):
            _LOGGER.warning(
                "Network scan for miners timed out after %s seconds", SCAN_TIMEOUT
            )
            self._discovered = []
        except Exception:
            _LOGGER.warning("Miner network scan failed", exc_info=True)
            self._discovered = []
        finally:
            self._scan_task = None
            self._scan_done = True

        return self.async_show_progress_done(next_step_id="scan_result")

    def _show_scan_result_form(self, errors=None):
        """Render the scan-result form (dropdown when miners were found)."""
        schema_data = {}
        if self._discovered:
            options = [
                {"value": str(miner.ip), "label": self._miner_label(miner)}
                for miner in self._discovered
            ]
            schema_data[vol.Required(CONF_SCAN_MINER)] = SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            errors = errors or {"base": "no_miners_found"}
        schema_data[vol.Optional(CONF_SCAN_NETWORK, default="")] = str
        schema_data[vol.Optional(CONF_RESCAN, default=False)] = bool
        return self.async_show_form(
            step_id="scan_result",
            data_schema=vol.Schema(schema_data),
            errors=errors,
        )

    async def async_step_scan_result(self, user_input=None):
        """Let the user pick a discovered miner, rescan or set a CIDR."""
        if user_input is None:
            return self._show_scan_result_form()

        wants_rescan = user_input.get(CONF_RESCAN) or CONF_SCAN_MINER not in user_input

        if wants_rescan:
            custom_net, cidr_error = _validate_custom_cidr(
                user_input.get(CONF_SCAN_NETWORK)
            )
            if cidr_error:
                return self._show_scan_result_form({"base": cidr_error})
            self._custom_net = custom_net
            self._scan_done = False
            return await self.async_step_scan()

        selected_ip = user_input[CONF_SCAN_MINER]
        miner = next(
            (
                m
                for m in (self._discovered or [])
                if str(m.ip) == selected_ip
            ),
            None,
        )
        if miner is None:
            return self._show_scan_result_form({"base": "invalid_selection"})

        self._miner = miner
        self._data[CONF_IP] = selected_ip
        self._scan_done = False
        return await self.async_step_login()

    async def async_step_login(self, user_input=None):
        """Get miner login credentials."""
        if user_input is None:
            user_input = {}

        # Detect BitAxe miners and skip credential prompts
        if self._miner.make == MinerMake.BITAXE:
            return await self.async_step_title()

        schema_data = {}

        if self._miner.rpc is not None:
            if self._miner.rpc.pwd is not None:
                schema_data[
                    vol.Optional(
                        CONF_RPC_PASSWORD,
                        default=user_input.get(
                            CONF_RPC_PASSWORD,
                            (
                                self._miner.rpc.pwd
                                if self._miner.api.pwd is not None
                                else ""
                            ),
                        ),
                    )
                ] = TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                )

        if self._miner.web is not None:
            schema_data[
                vol.Optional(
                    CONF_WEB_USERNAME,
                    default=user_input.get(CONF_WEB_USERNAME, self._miner.web.username),
                )
            ] = str
            schema_data[
                vol.Optional(
                    CONF_WEB_PASSWORD,
                    default=user_input.get(
                        CONF_WEB_PASSWORD,
                        self._miner.web.pwd if self._miner.web.pwd is not None else "",
                    ),
                )
            ] = TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD, autocomplete="current-password"
                )
            )

        if self._miner.ssh is not None:
            schema_data[
                vol.Required(
                    CONF_SSH_USERNAME,
                    default=user_input.get(CONF_SSH_USERNAME, self._miner.ssh.username),
                )
            ] = str
            schema_data[
                vol.Optional(
                    CONF_SSH_PASSWORD,
                    default=user_input.get(
                        CONF_SSH_PASSWORD,
                        self._miner.ssh.pwd if self._miner.ssh.pwd is not None else "",
                    ),
                )
            ] = TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD, autocomplete="current-password"
                )
            )

        schema = vol.Schema(schema_data)
        if not user_input:
            if len(schema_data) == 0:
                # No credentials needed, check if Avalon miner
                if _is_avalon_miner(self._miner):
                    return await self.async_step_avalon_options()
                return await self.async_step_title()
            return self.async_show_form(step_id="login", data_schema=schema)

        self._data.update(user_input)

        # Check if Avalon miner to show options
        if _is_avalon_miner(self._miner):
            return await self.async_step_avalon_options()
        return await self.async_step_title()

    async def async_step_avalon_options(self, user_input=None):
        """Get Avalon miner control options."""
        if user_input is None:
            user_input = {}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_AVALON_CONTROL_MODE,
                    default=user_input.get(CONF_AVALON_CONTROL_MODE, AVALON_MODE_FULL),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {
                                "value": AVALON_MODE_SIMPLE,
                                "label": "Simple (pyasic only)",
                            },
                            {
                                "value": AVALON_MODE_FULL,
                                "label": "Full (CGMiner API control)",
                            },
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        if not user_input:
            return self.async_show_form(
                step_id="avalon_options", data_schema=data_schema
            )

        self._data.update(user_input)
        return await self.async_step_title()

    async def async_step_title(self, user_input=None):
        """Get entity title."""
        if self._miner.api is not None:
            if self._miner.api.pwd is not None:
                self._miner.api.pwd = self._data.get(CONF_RPC_PASSWORD, "")

        if self._miner.web is not None:
            self._miner.web.username = self._data.get(CONF_WEB_USERNAME, "")
            self._miner.web.pwd = self._data.get(CONF_WEB_PASSWORD, "")

        if self._miner.ssh is not None:
            self._miner.ssh.username = self._data.get(CONF_SSH_USERNAME, "")
            self._miner.ssh.pwd = self._data.get(CONF_SSH_PASSWORD, "")

        title = await self._miner.get_hostname()

        if user_input is None:
            user_input = {}

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_TITLE,
                    default=user_input.get(CONF_TITLE, title),
                ): str,
            }
        )
        if not user_input:
            return self.async_show_form(step_id="title", data_schema=data_schema)

        self._data.update(user_input)

        # Prevent duplicate entries for the same miner: prefer MAC address
        # as stable identity, fall back to the IP.
        mac = None
        if hasattr(self._miner, "get_mac"):
            try:
                mac = await asyncio.wait_for(self._miner.get_mac(), timeout=10)
            except (TimeoutError, asyncio.TimeoutError):
                mac = None

        if mac:
            unique_id = str(mac).strip().lower()
        else:
            unique_id = f"{DOMAIN}-{self._data[CONF_IP]}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=self._data[CONF_TITLE], data=self._data)

    async def async_step_discovery(self, discovery_info):
        """Handle discovery."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        has_devices = await _async_has_devices(self.hass)
        if not has_devices:
            return self.async_abort(reason="no_devices_found")

        return await self.async_step_user()
