"""CGMiner hashboard power controls for the Avalon 1246."""

import asyncio
import contextlib
import logging
import re

_LOGGER = logging.getLogger(__name__)


def is_avalon_1246(make: str | None, model: str | None) -> bool:
    """Match the model names reported by pyasic and cached by the integration."""
    model = (model or "").lower()
    return model in {"avalon 1246", "avalonminer 1246"} or (
        "avalon" in (make or "").lower() and model in {"1246", "a1246"}
    )


async def _send_command(ip: str, command: str) -> str:
    """Read one short-lived, plain-text CGMiner response."""
    async with asyncio.timeout(30):
        reader, writer = await asyncio.open_connection(ip, 4028)
        try:
            writer.write(command.encode("ascii"))
            await writer.drain()
            try:
                reply = await reader.readuntil(b"\0")
            except asyncio.IncompleteReadError as err:
                reply = err.partial
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
        match = re.search(r"\bPS\[0\s+\d+\s+\d+\s+(\d+)(?:\s|\])", reply)
        if match:
            return int(match[1]) > 100
    return None


async def set_hashpower(ip: str, enabled: bool) -> None:
    """Power off the hashboards or reboot the controller to resume mining."""
    command = "ascset|0,reboot,0" if enabled else "ascset|0,hashpower,0"
    reply = await _send_command(ip, command)
    # Reboot can close the connection without sending a status reply.
    if enabled and not reply:
        return
    if not reply.startswith(("STATUS=I,", "STATUS=S,")):
        raise OSError("Avalon did not acknowledge the command")
