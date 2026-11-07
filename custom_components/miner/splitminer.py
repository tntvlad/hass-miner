"""SplitMiner / generic cgminer-API virtual miner support.

SplitMiner exposes one CG-API (cgminer 4.11.1 text protocol) per virtual
miner on its own port (4028, 4029, ...). pyasic does not detect these, so
this module provides detection + data fetching using the text protocol.
"""

import asyncio
import contextlib
import logging

_LOGGER = logging.getLogger(__name__)


class SplitMiner:
    """Minimal sentinel standing in for a pyasic miner object."""

    _splitminer = True

    def __init__(self, ip: str, fw_ver: str | None = None, port: int = 4028):
        """Init."""
        self.ip = ip
        self.port = port
        self.make = "SplitMiner"
        self.model = "Virtual Miner"
        self.fw_ver = fw_ver or "cgminer 4.11.1"
        self.api = None
        self.web = None
        self.ssh = None
        self.rpc = None
        self.raw_model = "Virtual Miner"
        self.supports_shutdown = False
        self.supports_autotuning = False
        self.supports_power_modes = False
        self.expected_fans = 0
        self.expected_hashboards = None

    @property
    def expected_hashboards(self):
        """Expected hashboards."""
        return None

    async def get_hostname(self):
        """Hostname."""
        return "SplitMiner VM"

    async def get_mac(self):
        """Mac."""
        return None

    def __repr__(self):
        """Repr."""
        return f"SplitMiner({self.ip}:{self.port})"

    def __lt__(self, other):
        """Lt."""
        return str(getattr(self, "ip", "")) < str(getattr(other, "ip", ""))


async def _cg_command(ip: str, port: int, command: str, timeout: int = 10) -> str:
    """Send a text cgminer command and return the raw response."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
    except Exception as e:
        _LOGGER.debug("SplitMiner %s:%s: connect failed for %s: %s", ip, port, command, e)
        return ""
    try:
        writer.write((command + "\n").encode("utf-8"))
        await writer.drain()
        data = b""
        timeouts = 0
        while timeouts < 3:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=2)
                if not chunk:
                    break
                data += chunk
            except asyncio.TimeoutError:
                timeouts += 1
        return data.decode("utf-8", errors="ignore")
    except Exception as e:
        _LOGGER.debug("SplitMiner %s:%s: command %s failed: %s", ip, port, command, e)
        return ""
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def _parse_kv_line(text: str) -> dict:
    """Parse a cgminer text line like 'KEY=val,KEY2=val2' into a dict."""
    result = {}
    for part in text.split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            result[k.strip()] = v.strip()
    return result


def _parse_sections(text: str) -> dict:
    """Parse cgminer multi-line text response into {SECTION: [dict,...]}."""
    sections = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" in line and "," not in line.split("=")[0]:
            # section header like STATUS=S,...
            pass
        # Detect section name: lines like "SUMMARY=0,Elapsed=..."
        if "=" in line:
            key = line.split("=", 1)[0].strip().upper()
            # known sections
            if key in ("STATUS", "SUMMARY", "DEVS", "POOLS", "VERSION", "COIN"):
                rest = line.split("=", 1)[1]
                # rest may be "0,Elapsed=..." -> strip leading index
                if "," in rest and not rest.split(",")[0].isalpha():
                    # leading index like "0,Elapsed=..."
                    parts = rest.split(",", 1)
                    if len(parts) == 2 and "=" in parts[1]:
                        rest = parts[1]
                d = _parse_kv_line(rest)
                sections.setdefault(key, []).append(d)
    return sections


async def detect_splitminer(ip: str, port: int = 4028, timeout: int = 10) -> str | None:
    """Return version string if host exposes a cgminer API (splitminer VM)."""
    text = await _cg_command(ip, port, "version", timeout=timeout)
    if "cgminer" not in text.lower():
        return None
    # ensure summary/devs respond
    summ = await _cg_command(ip, port, "summary", timeout=timeout)
    if "MHSav" not in summ and "MHS av" not in summ and "MHSav" not in summ:
        # still accept if summary present
        if "SUMMARY" not in summ.upper():
            return None
    return "cgminer 4.11.1"


async def fetch_splitminer_data(ip: str, port: int = 4028, timeout: int = 10) -> dict | None:
    """Fetch a coordinator-compatible data dict from a splitminer virtual miner."""
    await _cg_command(ip, port, "version", timeout=timeout)
    summary_text = await _cg_command(ip, port, "summary", timeout=timeout)
    devs_text = await _cg_command(ip, port, "devs", timeout=timeout)

    if "SUMMARY" not in summary_text.upper():
        return None

    sections = _parse_sections(summary_text)
    summ = sections.get("SUMMARY", [{}])[0]

    def to_th(hs):
        try:
            return round(float(hs) / 1e12, 4)
        except (TypeError, ValueError):
            return None

    # MHSav in MH/s
    mhs = summ.get("MHSav") or summ.get("MHS av") or summ.get("MHS 5s") or 0
    hashrate = to_th(mhs)

    devs_sections = _parse_sections(devs_text)
    devs = devs_sections.get("DEVS", [])

    temps = []
    for d in devs:
        t = d.get("Temp")
        if t is not None:
            with contextlib.suppress(ValueError):
                temps.append(float(t))
    avg_temp = round(sum(temps) / len(temps), 2) if temps else None

    board_sensors = {}
    for i, d in enumerate(devs):
        idx = d.get("ID", i)
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            idx = i
        mh = d.get("MHSav") or d.get("MHS av") or d.get("MHS 5s")
        board_sensors[idx] = {
            "board_temperature": float(d.get("Temp")) if d.get("Temp") is not None else None,
            "board_temperature_min": None,
            "chip_temperature": None,
            "chip_temperature_min": None,
            "inlet_temperature": None,
            "outlet_temperature": None,
            "water_inlet_temperature": None,
            "water_outlet_temperature": None,
            "board_hashrate": to_th(mh) if mh is not None else None,
        }

    summ.get("Accepted")
    summ.get("Rejected")

    data = {
        "hostname": None,
        "mac": None,
        "make": "SplitMiner",
        "model": "Virtual Miner",
        "ip": ip,
        "is_mining": True,
        "fw_ver": "cgminer 4.11.1",
        "miner_sensors": {
            "hashrate": hashrate,
            "ideal_hashrate": hashrate,
            "active_preset_name": None,
            "temperature": avg_temp,
            "power_limit": 0,
            "miner_consumption": None,
            "efficiency": None,
        },
        "board_sensors": board_sensors,
        "fan_sensors": {},
        "config": {},
        "power_limit_range": {"min": 15, "max": 10000},
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
        "bitaxe_frequency": None,
        "bitaxe_min_frequency": None,
        "bitaxe_max_frequency": None,
        "baikal_best_share": None,
        "baikal_found_blocks": None,
    }
    return data
