"""Regressions for VNish totals with incomplete pyasic board data.

Run with the project's dependencies installed:
    python -m unittest discover -s tests -v
"""

import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.miner import coordinator as coordinator_module
from custom_components.miner.patch import apply_pydantic_property_patch


def setUpModule():
    """Use the integration's Python 3.14 compatibility patch before pyasic loads."""
    apply_pydantic_property_patch()


class CoordinatorHashrateTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the actual coordinator update without contacting any miner."""

    async def update(self, raw_hashrate, fw_ver="VNish 1.3.6", web=None):
        """Return sensor data for a miner whose third board was omitted by pyasic."""
        # VNish physical slots 1, 2, 4 can be read as slots 1, 2, 3 (missing)
        # when chain_acs* fields are absent. The reported total is independent.
        boards = [
            SimpleNamespace(slot=slot, hashrate=rate, temp=None, chip_temp=None)
            for slot, rate in enumerate((19.6, 19.69, None))
        ]
        miner_data = SimpleNamespace(
            hostname="test-miner",
            mac=None,
            make="Antminer",
            model="S19 Pro",
            is_mining=True,
            fw_ver=fw_ver,
            raw_hashrate=raw_hashrate,
            hashrate=39.29,
            expected_hashrate=59.6,
            hashboards=boards,
            temperature_avg=None,
            wattage=1678,
            wattage_limit=1680,
            efficiency_fract=None,
            fans=[],
            config=None,
        )
        miner = SimpleNamespace(
            ip="192.0.2.1",
            make="Antminer",
            model="S19 Pro",
            web=web,
            get_data=AsyncMock(return_value=miner_data),
        )
        # Only fetching/persistence are mocked; run the full update method,
        # including firmware detection, normalization and efficiency calculation.
        coordinator = MagicMock(spec=coordinator_module.MinerCoordinator)
        coordinator.miner = miner
        coordinator.config_entry = SimpleNamespace(data={})
        coordinator.get_miner = AsyncMock(return_value=miner)
        coordinator.data = {}

        with ExitStack() as stack:
            for name in (
                "_fetch_vnish_preset",
                "_fetch_vnish_summary",
                "_fetch_vnish_overclock_limits",
                "_fetch_vnish_overclock_settings",
            ):
                stack.enter_context(
                    patch.object(
                        coordinator_module, name, new=AsyncMock(return_value=None)
                    )
                )
            stack.enter_context(
                patch.object(
                    coordinator_module,
                    "_fetch_vnish_temperatures",
                    new=AsyncMock(
                        return_value={
                            0: {"board_temperature": 50, "chip_temperature": 70}
                        }
                    ),
                )
            )
            data = await coordinator_module.MinerCoordinator._async_update_data(
                coordinator
            )

        return data["miner_sensors"]

    async def test_vnish_total_includes_omitted_board(self):
        """Use the total and correct efficiency instead of summing two boards."""
        sensors = await self.update(58.403175)
        self.assertEqual(sensors["hashrate"], 58.4)
        self.assertEqual(sensors["efficiency"], 28.73)

    async def test_vnish_zero_total_is_preserved(self):
        """Do not replace a stopped miner's zero with stale nonzero board data."""
        sensors = await self.update(0)
        self.assertEqual(sensors["hashrate"], 0)

    async def test_vnish_missing_total_stays_unknown(self):
        """Do not report the incomplete board sum when the total is unavailable."""
        sensors = await self.update(None)
        self.assertIsNone(sensors["hashrate"])

    async def test_non_vnish_keeps_existing_board_sum(self):
        """Preserve other firmware's hashrate and efficiency calculation."""
        sensors = await self.update(58.403175, fw_ver="stock")
        self.assertEqual(sensors["hashrate"], 39.29)
        self.assertEqual(sensors["efficiency"], 42.71)

    async def test_vnish_retains_hashrate_normalization(self):
        """Keep the existing H/s-to-TH/s conversion for unscaled totals."""
        sensors = await self.update(58_403_175_000_000)
        self.assertEqual(sensors["hashrate"], 58.4)
        self.assertEqual(sensors["efficiency"], 28.73)

    async def test_vnish_detected_from_web_api(self):
        """Use the total even when the firmware version omits the VNish name."""
        web = type("VNishWebAPI", (), {})()
        sensors = await self.update(58.403175, fw_ver="1.3.6", web=web)
        self.assertEqual(sensors["hashrate"], 58.4)


if __name__ == "__main__":
    unittest.main()
