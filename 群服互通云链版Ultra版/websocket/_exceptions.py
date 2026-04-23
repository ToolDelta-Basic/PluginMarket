"""
_exceptions.py
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


class WebSocketException(Exception):
    """Base exception for websocket-client errors."""

    __slots__ = ()


class WebSocketProtocolException(WebSocketException):
    """Raised when the WebSocket protocol is invalid."""

    __slots__ = ()


class WebSocketPayloadException(WebSocketException):
    """Raised when a WebSocket payload is invalid."""

    __slots__ = ()


class WebSocketConnectionClosedException(WebSocketException):
    """Raised when the remote host closed the connection."""

    __slots__ = ()


class WebSocketTimeoutException(WebSocketException):
    """Raised on socket timeout during reads or writes."""

    __slots__ = ()


class WebSocketProxyException(WebSocketException):
    """Raised when a proxy-related error occurs."""

    __slots__ = ()


class WebSocketBadStatusException(WebSocketException):
    """Raised when the handshake returns an unexpected HTTP status code."""

    def __init__(
        self,
        message: str,
        status_code: int,
        status_message=None,
        resp_headers=None,
        resp_body=None,
    ):
        """Store the HTTP status details that caused the handshake failure."""
        super().__init__(message)
        self.status_code = status_code
        self.resp_headers = resp_headers
        self.resp_body = resp_body


class WebSocketAddressException(WebSocketException):
    """Raised when websocket address information cannot be resolved."""

    __slots__ = ()
