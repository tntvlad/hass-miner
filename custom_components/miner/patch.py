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
        if hasattr(_generate_schema, '_hass_property_patched'):
            _PATCH_LOGGER.debug("Pydantic already patched for property handling")
            return True
        
        # Store original method
        original_unknown_type_schema = _generate_schema.GenerateSchema._unknown_type_schema
        
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
        _generate_schema.GenerateSchema._unknown_type_schema = patched_unknown_type_schema
        _generate_schema._hass_property_patched = True
        _PATCH_LOGGER.info("Applied pydantic property patch for Python 3.14 compatibility")
        return True
        
    except Exception as e:
        _PATCH_LOGGER.warning(f"Failed to apply pydantic property patch: {e}")
        return False
