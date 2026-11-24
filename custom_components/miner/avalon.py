"""CGMiner hashboard power controls for the Avalon 1246."""

import asyncio
import contextlib
import logging
import re

_LOGGER = logging.getLogger(__name__)

WORK_MODES_1246 = {"Normal": 0, "High Performance": 1}


def is_avalon_1246(make: str | None, model: str | None) -> bool:
    """Match the model names reported by pyasic and cached by the integration."""
    model = (model or "").lower()
    return model in {"avalon 1246", "avalonminer 1246"} or (
        "avalon" in (make or "").lower() and model in {"1246", "a1246"}
    )


async def _send_command(ip: str, command: str, *, reboots: bool = False) -> str:
    """Read one short-lived, plain-text CGMiner response."""
    async with asyncio.timeout(30):
        reader, writer = await asyncio.open_connection(ip, 4028)
        try:
            writer.write(command.encode("ascii"))
            await writer.drain()
            try:
                reply = await asyncio.wait_for(
                    reader.readuntil(b"\0"), timeout=5 if reboots else 25
                )
            except asyncio.IncompleteReadError as err:
                reply = err.partial
            except (ConnectionResetError, TimeoutError):
                if not reboots:
                    raise
                # Reboot can interrupt the reply after the command was sent.
                reply = b""
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
    return reply.decode("ascii", errors="replace").rstrip("\0").strip()


async def fetch_hashpower(ip: str) -> bool | None:
    """Return whether the hashboards are drawing current."""
    try:
        reply = await _send_command(ip, "ascset|0,hashpower")
    except (OSError, TimeoutError, asyncio.LimitOverrunError) as err:
        _LOGGER.debug("Could not read Avalon hashboard power: %s", err)
        return None

    if reply.startswith(("STATUS=I,", "STATUS=S,")):
        # The first field is the PSU status code. Some units report a
        # nonzero code when the hashboards are powered off.
        match = re.search(r"\bPS\[\d+\s+\d+\s+\d+\s+(\d+)(?:\s|\])", reply)
        if match:
            return int(match[1]) > 100
    return None


async def set_hashpower(ip: str, enabled: bool) -> None:
    """Power off the hashboards or reboot the controller to resume mining."""
    command = "ascset|0,reboot,0" if enabled else "ascset|0,hashpower,0"
    reply = await _send_command(ip, command, reboots=enabled)
    # The next status poll determines whether mining actually resumed.
    if enabled and not reply:
        return
    if not reply.startswith(("STATUS=I,", "STATUS=S,")):
        raise OSError("Avalon did not acknowledge the command")


def _parse_workmode(reply: str) -> int | None:
    """Read the mode from an acknowledged CGMiner response."""
    if reply.startswith(("STATUS=I,", "STATUS=S,")):
        match = re.search(r"\bWORKMODE\[([01])\]", reply)
        if match:
            return int(match[1])
    return None


async def fetch_1246_workmode(ip: str) -> int | None:
    """Read the configured work mode."""
    try:
        reply = await _send_command(ip, "ascset|0,workmode,255")
    except (OSError, TimeoutError, asyncio.LimitOverrunError) as err:
        _LOGGER.debug("Could not read Avalon work mode: %s", err)
        return None
    return _parse_workmode(reply)


async def set_1246_workmode(ip: str, mode: int) -> None:
    """Set the work mode without rebooting the miner."""
    reply = await _send_command(ip, f"ascset|0,workmode,{mode}")
    if _parse_workmode(reply) != mode:
        raise OSError("Avalon did not acknowledge the requested work mode")
