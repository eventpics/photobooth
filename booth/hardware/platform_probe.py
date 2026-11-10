"""Detects whether we are running on real Raspberry Pi hardware.

Everything in this tool has a mock implementation so the web UI can be
developed and reviewed on a laptop. The probe decides which one is used.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_MODEL_FILE = Path("/proc/device-tree/model")


def is_raspberry_pi() -> bool:
    try:
        model = _MODEL_FILE.read_text(errors="ignore")
    except OSError:
        return False
    return "Raspberry Pi" in model


def pi_model() -> str:
    try:
        return _MODEL_FILE.read_text(errors="ignore").strip("\x00").strip()
    except OSError:
        return "unknown"


def resolve_mock(setting: str | bool) -> bool:
    """Turn the config value ("auto" | true | false) into a decision."""
    if isinstance(setting, bool):
        return setting
    if str(setting).lower() in {"1", "true", "yes"}:
        return True
    if str(setting).lower() in {"0", "false", "no"}:
        return False
    use_mock = not is_raspberry_pi()
    log.info("Mock mode auto-detected: %s (model: %s)", use_mock, pi_model())
    return use_mock
