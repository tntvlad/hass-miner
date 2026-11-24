"""Test Avalon 1246 hashboard power commands and responses."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import HomeAssistantError

from custom_components.miner import avalon, switch
from custom_components.miner.const import (
    AVALON_MODE_SIMPLE,
    CONF_AVALON_CONTROL_MODE,
    DOMAIN,
)


class AvalonHashpowerTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the plain-text API without contacting a miner."""

    def reply(self, data: bytes, *, eof: bool = True):
        """Supply a reply from a fake CGMiner connection."""
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        if eof:
            reader.feed_eof()
        writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
        connection = AsyncMock(return_value=(reader, writer))
        self.enterContext(patch.object(avalon.asyncio, "open_connection", connection))
        return connection, writer

    async def test_reads_hashboard_current(self):
        """Parse the current field from a NUL-terminated response."""
        connection, writer = self.reply(
            b"STATUS=I,Code=118,Msg=ASC 0 set info: PS[0 1220 1314 140 1839 1308]\0",
            eof=False,
        )
        self.assertIs(await avalon.fetch_hashpower("192.0.2.1"), True)
        connection.assert_awaited_once_with("192.0.2.1", 4028)
        writer.write.assert_called_once_with(b"ascset|0,hashpower")
        writer.close.assert_called_once()

    async def test_reports_powered_off_hashboards(self):
        """Read a response framed by connection close."""
        self.reply(b"STATUS=I,Msg=ASC 0 set info: PS[0 1220 0 0 0 1308]")
        self.assertIs(await avalon.fetch_hashpower("192.0.2.1"), False)

    async def test_reports_powered_off_with_nonzero_psu_status(self):
        """Read zero current from a 1246 PSU in its powered-off state."""
        self.reply(b"STATUS=I,Code=118,Msg=ASC 0 set info: PS[32 1214 4 0 0 1288]")
        self.assertIs(await avalon.fetch_hashpower("192.0.2.1"), False)

    async def test_invalid_power_reply_is_unknown(self):
        """Keep power state unknown when telemetry is missing."""
        self.reply(b"STATUS=I,Msg=ASC 0 set info: PS[0 1220 0]")
        self.assertIsNone(await avalon.fetch_hashpower("192.0.2.1"))

    async def test_stop_turns_off_hashboard_power(self):
        """Send the power-off command and accept its informational reply."""
        _, writer = self.reply(b"STATUS=I,Code=118,Msg=Power off hash now")
        await avalon.set_hashpower("192.0.2.1", False)
        writer.write.assert_called_once_with(b"ascset|0,hashpower,0")

    async def test_start_reboots_the_miner(self):
        """Allow the reboot to close the connection before it sends a reply."""
        _, writer = self.reply(b"")
        await avalon.set_hashpower("192.0.2.1", True)
        writer.write.assert_called_once_with(b"ascset|0,reboot,0")

    async def test_reboot_can_reset_connection_after_write(self):
        """Allow a reset while waiting for the firmware's reboot reply."""
        connection, writer = self.reply(b"", eof=False)
        reader, _ = connection.return_value
        reader.set_exception(ConnectionResetError())
        await avalon.set_hashpower("192.0.2.1", True)
        writer.drain.assert_awaited_once()

    async def test_reboot_connection_failure_still_raises(self):
        """Require a successful connection before accepting a missing reply."""
        connection, _ = self.reply(b"")
        connection.side_effect = ConnectionResetError()
        with self.assertRaises(ConnectionResetError):
            await avalon.set_hashpower("192.0.2.1", True)

    async def test_reboot_can_leave_connection_open_without_reply(self):
        """Allow the observed firmware to reboot without a reply or EOF."""
        _, writer = self.reply(b"", eof=False)

        async def timeout_wait(awaitable, *, timeout):
            awaitable.close()
            self.assertEqual(timeout, 5)
            raise TimeoutError

        with patch.object(avalon.asyncio, "wait_for", timeout_wait):
            await avalon.set_hashpower("192.0.2.1", True)
        writer.write.assert_called_once_with(b"ascset|0,reboot,0")
        writer.drain.assert_awaited_once()

    async def test_rejected_command_raises(self):
        """Surface a rejected command instead of reporting success."""
        self.reply(b"STATUS=E,Msg=Access denied")
        with self.assertRaises(OSError):
            await avalon.set_hashpower("192.0.2.1", True)

    async def test_reads_normal_workmode(self):
        """Parse the configured Normal mode from an observed response."""
        _, writer = self.reply(
            b"STATUS=I,Code=118,Msg=ASC 0 set info: WORKMODE[0] success"
        )
        self.assertEqual(await avalon.fetch_1246_workmode("192.0.2.1"), 0)
        writer.write.assert_called_once_with(b"ascset|0,workmode,255")

    async def test_sets_high_performance_workmode(self):
        """Require the firmware to acknowledge the requested mode."""
        _, writer = self.reply(
            b"STATUS=I,Code=118,Msg=ASC 0 set info: WORKMODE[1] success"
        )
        await avalon.set_1246_workmode("192.0.2.1", 1)
        writer.write.assert_called_once_with(b"ascset|0,workmode,1")

    async def test_wrong_workmode_acknowledgement_raises(self):
        """Surface a reply that acknowledges a different mode."""
        self.reply(b"STATUS=I,Code=118,Msg=ASC 0 set info: WORKMODE[0] success")
        with self.assertRaises(OSError):
            await avalon.set_1246_workmode("192.0.2.1", 1)

    def test_only_matches_avalon_1246(self):
        """Recognize the 1246 without enabling this control on other Avalons."""
        self.assertTrue(avalon.is_avalon_1246("AvalonMiner", "Avalon 1246"))
        self.assertTrue(avalon.is_avalon_1246("AvalonMiner", "1246"))
        self.assertFalse(avalon.is_avalon_1246("AvalonMiner", "Avalon Nano 3s"))
        self.assertFalse(avalon.is_avalon_1246("Antminer", "1246"))


class AvalonSwitchTests(unittest.IsolatedAsyncioTestCase):
    """Exercise Home Assistant switch setup and actions."""

    async def setup_switches(self, *, offline=False, options=None):
        """Set up an Avalon 1246 and return the entities and coordinator."""
        data = {"make": "AvalonMiner", "model": "Avalon 1246", "ip": "192.0.2.1"}
        entry = SimpleNamespace(entry_id="avalon", data=options or {})
        coordinator = SimpleNamespace(
            config_entry=entry,
            data=data,
            miner=(
                None if offline else SimpleNamespace(supports_shutdown=False, web=None)
            ),
            cached_profile=data,
            available=not offline,
            async_request_refresh=AsyncMock(),
        )
        hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: coordinator}})
        entities = []
        await switch.async_setup_entry(hass, entry, entities.extend)
        return entities, coordinator

    async def test_offline_setup_uses_existing_cached_identity(self):
        """Restore the same entity ID if setup happens with the miner offline."""
        entities, _ = await self.setup_switches(offline=True)
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].unique_id, "avalon-avalon-mining")
        self.assertFalse(entities[0].available)

    async def test_simple_mode_skips_switch(self):
        """Honor the configured read-only mode."""
        entities, _ = await self.setup_switches(
            options={CONF_AVALON_CONTROL_MODE: AVALON_MODE_SIMPLE}
        )
        self.assertEqual(entities, [])

    async def test_command_refreshes_state_and_reports_failure(self):
        """Refresh after a successful command and surface transport failures."""
        (entity,), coordinator = await self.setup_switches()
        with (
            patch.object(entity, "async_write_ha_state"),
            patch.object(switch, "set_hashpower", new_callable=AsyncMock) as command,
        ):
            await entity.async_turn_off()
            command.assert_awaited_once_with("192.0.2.1", False)
            coordinator.async_request_refresh.assert_awaited_once()

            command.side_effect = OSError("Connection refused")
            with self.assertRaises(HomeAssistantError):
                await entity.async_turn_on()
            coordinator.async_request_refresh.assert_awaited_once()

    async def test_switch_follows_polled_power_through_both_actions(self):
        """Follow firmware telemetry from off to on and back to off."""
        (entity,), coordinator = await self.setup_switches()

        async def refresh():
            coordinator.data["avalon_hashpower"] = command.call_args.args[1]
            entity._handle_coordinator_update()

        coordinator.data["avalon_hashpower"] = False
        coordinator.async_request_refresh.side_effect = refresh
        with (
            patch.object(entity, "async_write_ha_state"),
            patch.object(switch, "set_hashpower", new_callable=AsyncMock) as command,
        ):
            entity._handle_coordinator_update()
            self.assertIs(entity.is_on, False)
            await entity.async_turn_on()
            self.assertIs(entity.is_on, True)
            await entity.async_turn_off()
            self.assertIs(entity.is_on, False)
