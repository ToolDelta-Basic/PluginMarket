"""
_logging.py
websocket - WebSocket client library for Python

Copyright 2024 engn33r

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
from logging import NullHandler

_logger = logging.getLogger("websocket")
_logger.addHandler(NullHandler())

_TRACE_STATE = {"enabled": False}

__all__ = [
    "enableTrace",
    "dump",
    "error",
    "warning",
    "debug",
    "trace",
    "isEnabledForError",
    "isEnabledForDebug",
    "isEnabledForTrace",
]


def enableTrace(
    traceable: bool,
    handler: logging.StreamHandler = logging.StreamHandler(),
    level: str = "DEBUG",
) -> None:
    """
    Turn on/off the traceability.

    Parameters
    ----------
    traceable: bool
        If set to True, traceability is enabled.
    """
    _TRACE_STATE["enabled"] = traceable
    if traceable:
        _logger.addHandler(handler)
        _logger.setLevel(getattr(logging, level))


def dump(title: str, message: str) -> None:
    """Emit a formatted debug block when trace logging is enabled."""
    if _TRACE_STATE["enabled"]:
        _logger.debug("--- %s ---", title)
        _logger.debug(message)
        _logger.debug("-----------------------")


def error(msg: str, *args) -> None:
    """Log an error message."""
    _logger.error(msg, *args)


def warning(msg: str, *args) -> None:
    """Log a warning message."""
    _logger.warning(msg, *args)


def debug(msg: str, *args) -> None:
    """Log a debug message."""
    _logger.debug(msg, *args)


def info(msg: str, *args) -> None:
    """Log an informational message."""
    _logger.info(msg, *args)


def trace(msg: str) -> None:
    """Log a trace message when trace mode is enabled."""
    if _TRACE_STATE["enabled"]:
        _logger.debug(msg)


def isEnabledForError() -> bool:
    """Return whether error logging is currently enabled."""
    return _logger.isEnabledFor(logging.ERROR)


def isEnabledForDebug() -> bool:
    """Return whether debug logging is currently enabled."""
    return _logger.isEnabledFor(logging.DEBUG)


def isEnabledForTrace() -> bool:
    """Return whether trace logging is currently enabled."""
    return _TRACE_STATE["enabled"]
