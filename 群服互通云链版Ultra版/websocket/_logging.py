import logging

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

_logger = logging.getLogger("websocket")
try:
    from logging import NullHandler
except ImportError:

    class NullHandler(logging.Handler):
        def emit(self, record) -> None:
            return None


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
    if _TRACE_STATE["enabled"]:
        _logger.debug(f"--- {title} ---")
        _logger.debug(message)
        _logger.debug("-----------------------")


def error(msg: str, *args) -> None:
    _logger.error(msg, *args)


def warning(msg: str, *args) -> None:
    _logger.warning(msg, *args)


def debug(msg: str, *args) -> None:
    _logger.debug(msg, *args)


def info(msg: str, *args) -> None:
    _logger.info(msg, *args)


def trace(msg: str) -> None:
    if _TRACE_STATE["enabled"]:
        _logger.debug(msg)


def isEnabledForError() -> bool:
    return _logger.isEnabledFor(logging.ERROR)


def isEnabledForDebug() -> bool:
    return _logger.isEnabledFor(logging.DEBUG)


def isEnabledForTrace() -> bool:
    return _TRACE_STATE["enabled"]
