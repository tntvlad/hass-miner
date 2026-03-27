"""Patch annoying home assistant dependency handling and fix pyasic issues."""
from __future__ import annotations

import logging
import os
import site
import sys
from subprocess import PIPE
from subprocess import Popen

from homeassistant.util.package import _LOGGER
from homeassistant.util.package import is_virtual_env

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


def apply_whatsminer_patch():
    """Monkey-patch pyasic to fix Whatsminer privileged command issue.
    
    In pyasic 0.78.x, the open_api() fallback was disabled/commented out
    in send_privileged_command(). This patch restores the original behavior
    from pyasic 0.75.0 which automatically enables the Whatsminer API when
    a "can't access write cmd" error occurs.
    """
    try:
        from pyasic.rpc.btminer import BTMinerRPCAPI
        from pyasic.errors import APIError
    except ImportError:
        _PATCH_LOGGER.warning("Could not import pyasic.rpc.btminer for patching")
        return False

    # Check if already patched
    if hasattr(BTMinerRPCAPI, '_hass_miner_patched'):
        _PATCH_LOGGER.debug("BTMinerRPCAPI already patched")
        return True

    # Store reference to the original internal method
    _original_send_privileged = BTMinerRPCAPI._send_privileged_command

    async def patched_send_privileged_command(
        self,
        command: str,
        ignore_errors: bool = False,
        timeout: int = 10,
        **kwargs,
    ) -> dict:
        """Patched send_privileged_command with open_api() fallback restored."""
        try:
            return await _original_send_privileged(
                self,
                command=command,
                ignore_errors=ignore_errors,
                timeout=timeout,
                **kwargs
            )
        except APIError as e:
            if e.message != "can't access write cmd":
                raise
            # Restore the open_api() fallback that was removed in pyasic 0.78.x
            _PATCH_LOGGER.info(
                "Whatsminer API access denied, attempting to enable API via open_api()"
            )
            try:
                await self.open_api()
            except Exception as ex:
                _PATCH_LOGGER.error(f"Failed to open Whatsminer API: {ex}")
                raise APIError("Failed to open whatsminer API.") from ex
            # Retry the command after enabling API
            return await _original_send_privileged(
                self,
                command=command,
                ignore_errors=ignore_errors,
                timeout=timeout,
                **kwargs
            )

    # Apply the patch
    BTMinerRPCAPI.send_privileged_command = patched_send_privileged_command
    BTMinerRPCAPI._hass_miner_patched = True
    _PATCH_LOGGER.info("Applied Whatsminer API patch to BTMinerRPCAPI")
    return True
