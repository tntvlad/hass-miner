"""Baikal BK-X miner support (sgminer 5.6.6-l based).

The Baikal BK-X is an FPGA miner running sgminer. pyasic does not detect it,
so this module provides a lightweight detection + data fetcher that the
integration uses directly (mirroring the direct-API fetchers for VNish/BOS).
"""

import asyncio
import json
import logging

_LOGGER = logging.getLogger(__name__)

# Hashboard count from the most recent sgminer "devs" reply, per IP. The
# platform set-up code reads it off the sentinel before the next poll.
_LAST_BOARD_COUNT: dict[str, int] = {}


class BaikalMiner:
    """Minimal sentinel standing in for a pyasic miner object."""

    _baikal = True

    def __init__(self, ip: str, fw_ver: str | None = None, port: int = 4028):
        """Initialize."""
        self.ip = ip
        self.port = port
        self.make = "Baikal"
        self.model = "BK-X"
        self.raw_model = "BK-X"
        self.fw_ver = fw_ver
        self.api = None
        self.web = None
        self.ssh = None
        self.rpc = None
        # Capability flags the entity platforms read directly off the miner
        # object; sgminer exposes no pause/autotune control for the BK-X.
        self.supports_shutdown = False
        self.supports_autotuning = False
        self.supports_power_modes = False
        self.expected_fans = 2

    @property
    def expected_hashboards(self) -> int:
        """Return the hashboard count seen in the last sgminer poll."""
        return _LAST_BOARD_COUNT.get(self.ip, 3)

    async def get_hostname(self):
        """Return hostname."""
        return "Baikal BK-X"

    async def get_mac(self):
        """Return MAC."""
        return None

    def __repr__(self):
        """Repr."""
        return f"BaikalMiner({self.ip})"

    def __lt__(self, other):
        """Less than."""
        return str(getattr(self, "ip", "")) < str(getattr(other, "ip", ""))


async def _sgminer_command(ip: str, command: str, port: int = 4028, timeout: int = 10):
    """Send a single sgminer/cgminer API command and return parsed JSON."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
    except Exception as e:
        _LOGGER.debug("Baikal %s: connect failed for %s: %s", ip, command, e)
        return None
    try:
        writer.write((json.dumps({"command": command}) + "\n").encode("utf-8"))
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
        text = data.decode("utf-8", errors="ignore").replace("\x00", "").strip()
        return json.loads(text) if text else None
    except Exception as e:
        _LOGGER.debug("Baikal %s: command %s failed: %s", ip, command, e)
        return None
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def detect_baikal(ip: str, port: int = 4028, timeout: int = 10) -> str | None:
    """Return the sgminer version string if the host is a Baikal BK-X."""
    resp = await _sgminer_command(ip, "version", port=port, timeout=timeout)
    if not resp:
        return None
    try:
        ver = resp["VERSION"][0]
    except (KeyError, IndexError, TypeError):
        return None
    miner = str(ver.get("Miner", "") or ver.get("SGMiner", "") or "")
    if "sgminer" not in miner.lower():
        return None
    # Baikal devices report BKLU in devs
    devs = await _sgminer_command(ip, "devs", port=port, timeout=timeout)
    if devs:
        try:
            names = {d.get("Name") for d in devs.get("DEVS", [])}
        except Exception:
            names = set()
        if "BKLU" not in names and not any("BKLU" in str(n).upper() for n in names):
            # Still allow if sgminer present; but prefer BKLU confirmation
            pass
    return miner


async def fetch_baikal_data(ip: str, port: int = 4028, timeout: int = 10) -> dict | None:
    """Fetch a coordinator-compatible data dict from a Baikal BK-X."""
    version_resp = await _sgminer_command(ip, "version", port=port, timeout=timeout)
    summary_resp = await _sgminer_command(ip, "summary", port=port, timeout=timeout)
    devs_resp = await _sgminer_command(ip, "devs", port=port, timeout=timeout)
    await _sgminer_command(ip, "pools", timeout=timeout)

    if not summary_resp:
        return None

    try:
        ver = version_resp["VERSION"][0] if version_resp else {}
    except (KeyError, IndexError, TypeError):
        ver = {}
    fw_ver = ver.get("Miner") or ver.get("SGMiner") or "sgminer 5.6.6-l"

    try:
        summ = summary_resp["SUMMARY"][0]
    except (KeyError, IndexError, TypeError):
        summ = {}

    def to_th(mhs):
        try:
            return round(float(mhs) / 1e6, 4)
        except (TypeError, ValueError):
            return None

    hashrate = to_th(summ.get("MHS av") or summ.get("MHS 5s"))
    ideal = to_th(summ.get("MHS 5s"))

    devs = []
    try:
        devs = devs_resp.get("DEVS", []) if devs_resp else []
    except Exception:
        devs = []
    if devs:
        _LAST_BOARD_COUNT[ip] = len(devs)

    temps = [d.get("Temperature") for d in devs if d.get("Temperature") is not None]
    avg_temp = round(sum(temps) / len(temps), 2) if temps else None

    board_sensors = {}
    for d in devs:
        idx = d.get("ASC", d.get("ID", len(board_sensors)))
        mh = to_th(d.get("MHS 5s") or d.get("MHS av"))
        board_sensors[idx] = {
            "board_temperature": d.get("Temperature"),
            "board_temperature_min": None,
            "chip_temperature": None,
            "chip_temperature_min": None,
            "inlet_temperature": None,
            "outlet_temperature": None,
            "water_inlet_temperature": None,
            "water_outlet_temperature": None,
            "board_hashrate": mh,
        }

    best_share = summ.get("Best Share")
    found_blocks = summ.get("Found Blocks")

    data = {
        "hostname": None,
        "mac": None,
        "make": "Baikal",
        "model": "BK-X",
        "ip": ip,
        "is_mining": True,
        "fw_ver": fw_ver,
        "miner_sensors": {
            "hashrate": hashrate,
            "ideal_hashrate": ideal,
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
        "baikal_best_share": best_share,
        "baikal_found_blocks": found_blocks,
    }
    return data
