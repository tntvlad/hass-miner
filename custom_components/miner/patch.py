"""Patch annoying home assistant dependency handling and fix pyasic issues."""

from __future__ import annotations

import contextlib
import logging
import os
import site
import sys
from subprocess import PIPE, Popen

from homeassistant.util.package import _LOGGER, is_virtual_env

_PATCH_LOGGER = logging.getLogger(__name__)

_UV_ENV_PYTHON_VARS = (
    "UV_SYSTEM_PYTHON",
    "UV_PYTHON",
)


# Copy-paste of home assistant core install, but pre-releases are supported
def install_package(
    package: str,
    upgrade: bool = True,
    target: str | None = None,
    constraints: str | None = None,
    timeout: int | None = None,
    force_reinstall: bool = False,
    no_deps: bool = False,
) -> bool:
    """Install a package on PyPi. Accepts pip compatible package strings.

    Return boolean if install successful.
    """
    _LOGGER.info("Attempting install of %s", package)
    env = os.environ.copy()
    args = [
        sys.executable,
        "-m",
        "uv",
        "pip",
        "install",
        "--quiet",
        package,
        # Allow prereleases in sub-packages
        "--prerelease=allow",
        # We need to use unsafe-first-match for custom components
        # which can use a different version of a package than the one
        # we have built the wheel for.
        "--index-strategy",
        "unsafe-first-match",
    ]
    if timeout:
        env["HTTP_TIMEOUT"] = str(timeout)
    if upgrade:
        args.append("--upgrade")
    if force_reinstall:
        args.append("--reinstall")
    if no_deps:
        args.append("--no-deps")
    if constraints is not None:
        args += ["--constraint", constraints]
    if target:
        abs_target = os.path.abspath(target)
        args += ["--target", abs_target]
    elif (
        not is_virtual_env()
        and not (any(var in env for var in _UV_ENV_PYTHON_VARS))
        and (abs_target := site.getusersitepackages())
    ):
        # Pip compatibility
        # Uv has currently no support for --user
        # See https://github.com/astral-sh/uv/issues/2077
        # Using workaround to install to site-packages
        # https://github.com/astral-sh/uv/issues/2077#issuecomment-2150406001
        args += ["--python", sys.executable, "--target", abs_target]

    _LOGGER.debug("Running uv pip command: args=%s", args)
    with Popen(
        args,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
        close_fds=False,  # required for posix_spawn
    ) as process:
        _, stderr = process.communicate()
        if process.returncode != 0:
            _LOGGER.error(
                "Unable to install package %s: %s",
                package,
                stderr.decode("utf-8").lstrip().strip(),
            )
            return False

    return True


def apply_pydantic_property_patch():
    """Patch pydantic to handle property objects in Python 3.14+.

    Python 3.14 changed how property objects are represented in type annotations.
    This causes pydantic's schema generation to fail when it encounters
    @computed_field + @property decorated methods in pyasic's MinerData class.

    This patch modifies pydantic's _unknown_type_schema to return Any schema
    for property objects instead of raising an error.
    """
    import sys

    # Only needed for Python 3.14+
    if sys.version_info < (3, 14):
        _PATCH_LOGGER.debug("Python < 3.14, skipping pydantic property patch")
        return True

    try:
        from pydantic._internal import _generate_schema
        from pydantic_core import core_schema

        # Check if already patched
        if hasattr(_generate_schema, "_hass_property_patched"):
            _PATCH_LOGGER.debug("Pydantic already patched for property handling")
            return True

        # Store original method
        original_unknown_type_schema = (
            _generate_schema.GenerateSchema._unknown_type_schema
        )

        def patched_unknown_type_schema(self, obj):
            """Handle property objects gracefully instead of raising error."""
            # If it's a property object, return an Any schema
            if isinstance(obj, property):
                _PATCH_LOGGER.debug(f"Handling property object as Any type: {obj}")
                # Return a permissive "any" schema
                return core_schema.any_schema()
            # Otherwise use original implementation
            return original_unknown_type_schema(self, obj)

        # Apply patch
        _generate_schema.GenerateSchema._unknown_type_schema = (
            patched_unknown_type_schema
        )
        _generate_schema._hass_property_patched = True
        _PATCH_LOGGER.info(
            "Applied pydantic property patch for Python 3.14 compatibility"
        )
        return True

    except Exception as e:
        _PATCH_LOGGER.warning(f"Failed to apply pydantic property patch: {e}")
        return False


def apply_avalonminer_web_patch():
    """Patch AvalonMinerWebAPI._handle_multicommand to catch JSONDecodeError.

    In pyasic 0.78.0, _handle_multicommand only catches httpx.HTTPError but
    not json.JSONDecodeError (unlike send_command which catches both).  When
    Avalon Nano 3s miners return an empty web response, json.loads("") raises
    JSONDecodeError which crashes the entire get_data() call and prevents all
    entities from loading.
    """
    try:
        import json

        from pyasic.web.avalonminer import AvalonMinerWebAPI

        if hasattr(AvalonMinerWebAPI, "_hass_web_patched"):
            _PATCH_LOGGER.debug("AvalonMiner web API already patched")
            return True

        original_handle = AvalonMinerWebAPI._handle_multicommand

        async def patched_handle_multicommand(self, client, command):
            try:
                return await original_handle(self, client, command)
            except json.JSONDecodeError:
                _PATCH_LOGGER.debug(
                    f"AvalonMiner {self.ip}: ignoring JSONDecodeError "
                    f"for command '{command}'"
                )
                return {}

        AvalonMinerWebAPI._handle_multicommand = patched_handle_multicommand
        AvalonMinerWebAPI._hass_web_patched = True
        _PATCH_LOGGER.info(
            "Applied AvalonMiner web API patch (JSONDecodeError handling)"
        )
        return True

    except Exception as e:
        _PATCH_LOGGER.warning(f"Failed to apply AvalonMiner web patch: {e}")
        return False


def apply_whatsminer_power_limit_patch():
    """Restore the open_api + retry logic for Whatsminer privileged commands.

    In pyasic 0.78.0, the retry logic in BTMinerRPCAPI.send_privileged_command
    was commented out. When adjust_power_limit (or any privileged command)
    receives "can't access write cmd", the v0.75.0 code would call open_api()
    to unlock the API and retry. Without this, set_power_limit silently fails
    and the HA slider resets to the old value on the next coordinator update.
    """
    try:
        from pyasic.errors import APIError
        from pyasic.rpc.btminer import BTMinerRPCAPI

        if hasattr(BTMinerRPCAPI, "_hass_power_limit_patched"):
            _PATCH_LOGGER.debug("Whatsminer power limit already patched")
            return True

        original_send = BTMinerRPCAPI.send_privileged_command

        async def patched_send_privileged_command(
            self, command, ignore_errors=False, timeout=10, **kwargs
        ):
            try:
                return await original_send(
                    self,
                    command,
                    ignore_errors=ignore_errors,
                    timeout=timeout,
                    **kwargs,
                )
            except APIError as e:
                if not getattr(e, "message", str(e)) == "can't access write cmd":
                    raise
                # Restore v0.75.0 behavior: open API and retry
                _PATCH_LOGGER.info(
                    f"Whatsminer {self.ip}: got 'can't access write cmd', "
                    "attempting open_api + retry"
                )
                try:
                    await self.open_api()
                except Exception as oe:
                    raise APIError("Failed to open whatsminer API.") from oe
                return await original_send(
                    self,
                    command,
                    ignore_errors=ignore_errors,
                    timeout=timeout,
                    **kwargs,
                )

        BTMinerRPCAPI.send_privileged_command = patched_send_privileged_command
        BTMinerRPCAPI._hass_power_limit_patched = True
        _PATCH_LOGGER.info("Applied Whatsminer power limit patch (open_api retry)")
        return True

    except Exception as e:
        _PATCH_LOGGER.warning(f"Failed to apply Whatsminer power limit patch: {e}")
        return False


def apply_vnish_get_config_patch():
    """Patch VNish.get_config to handle autotune_presets returning a list.

    In pyasic 0.78.0, VNish.get_config() does web_presets_dict.get("presets", [])
    but autotune_presets() returns a JSON array (list), not a dict.  This causes
    AttributeError: 'list' object has no attribute 'get' which also breaks
    set_power_limit since it calls get_config() internally.
    """
    try:
        from pyasic import MinerConfig
        from pyasic.errors import APIError
        from pyasic.miners.backends.vnish import VNish

        if hasattr(VNish, "_hass_get_config_patched"):
            _PATCH_LOGGER.debug("VNish get_config already patched")
            return True

        async def patched_get_config(self) -> MinerConfig:
            try:
                web_settings = await self.web.settings()
                web_presets_raw = await self.web.autotune_presets()
                # autotune_presets() returns a list, not a dict
                if isinstance(web_presets_raw, list):
                    web_presets = web_presets_raw
                elif web_presets_raw:
                    web_presets = web_presets_raw.get("presets", [])
                else:
                    web_presets = []
                web_perf_summary = (await self.web.perf_summary()) or {}
            except APIError:
                return self.config or MinerConfig()
            self.config = MinerConfig.from_vnish(
                web_settings, web_presets, web_perf_summary
            )
            return self.config

        VNish.get_config = patched_get_config
        VNish._hass_get_config_patched = True
        _PATCH_LOGGER.info("Applied VNish get_config patch (list vs dict fix)")
        return True

    except Exception as e:
        _PATCH_LOGGER.warning(f"Failed to apply VNish get_config patch: {e}")
        return False


def apply_nerdqaxe_patch():
    """Teach pyasic about NerdQAxe (ESP-Miner) devices.

    The NerdQAxe++ runs ESP-Miner firmware, but its web UI titles the page
    "Nerd* Dashboard" instead of "AxeOS", so pyasic's factory never matches
    it and get_miner() returns None - the miner cannot be added at all.
    Its /api/system/info is the standard ESP-Miner payload, so handle it as
    a BitAxe with a NerdQAxe model name and both reported fans.
    """
    try:
        from pyasic.data import Fan
        from pyasic.device.models import MinerModelType
        from pyasic.errors import APIError
        from pyasic.miners.bitaxe import BitAxeGamma
        from pyasic.miners.factory import MINER_CLASSES, MinerFactory, MinerTypes

        if hasattr(MinerFactory, "_hass_nerdqaxe_patched"):
            _PATCH_LOGGER.debug("NerdQAxe patch already applied")
            return True

        class NerdQAxeModel(MinerModelType):
            """pyasic's DeviceInfo requires a MinerModelType, not a plain str."""

            NERDQAXE_PP = "NerdQAxe++"

            def __str__(self):
                return self.value

        class NerdQAxePP(BitAxeGamma):
            """NerdQAxe++ - ESP-Miner firmware with a non-AxeOS web UI."""

            raw_model = NerdQAxeModel.NERDQAXE_PP
            expected_fans = 2

            async def _get_fans(self, web_system_info: dict | None = None):
                if web_system_info is None:
                    with contextlib.suppress(APIError):
                        web_system_info = await self.web.system_info()
                if web_system_info is not None:
                    fans = [
                        Fan(speed=web_system_info[key])
                        for key in ("fanrpm", "fanrpm2")
                        if web_system_info.get(key) is not None
                    ]
                    if fans:
                        return fans
                return []

        # Reached because get_miner_model_bitaxe() returns "NerdQAxe++" below;
        # _select_miner_from_classes() upper-cases the key.
        MINER_CLASSES[MinerTypes.BITAXE]["NERDQAXE++"] = NerdQAxePP

        original_parse_web_type = MinerFactory._parse_web_type

        def patched_parse_web_type(web_text, web_resp):
            miner_type = original_parse_web_type(web_text, web_resp)
            if miner_type is not None:
                return miner_type
            if "Nerd* Dashboard" in web_text or "NerdQAxe" in web_text:
                return MinerTypes.BITAXE
            return None

        async def patched_get_miner_model_bitaxe(self, ip):
            web_json_data = await self.send_web_command(ip, "/api/system/info")
            if web_json_data is not None:
                try:
                    device_model = web_json_data.get("deviceModel")
                    if (
                        isinstance(device_model, str)
                        and "nerd" in device_model.lower()
                    ):
                        return device_model
                    miner_model = web_json_data["ASICModel"]
                    if miner_model == "":
                        return None
                    return miner_model
                except (TypeError, LookupError):
                    pass
            return None

        MinerFactory._parse_web_type = staticmethod(patched_parse_web_type)
        MinerFactory.get_miner_model_bitaxe = patched_get_miner_model_bitaxe
        MinerFactory._hass_nerdqaxe_patched = True
        _PATCH_LOGGER.info("Applied NerdQAxe patch (detection, model, fans)")
        return True

    except Exception as e:
        _PATCH_LOGGER.warning(f"Failed to apply NerdQAxe patch: {e}")
        return False
