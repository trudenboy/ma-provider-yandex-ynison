"""
Experimental native gRPC transport for Ynison.

The official mobile apps reach Ynison over gRPC at ``ynison.music.yandex.net``
instead of the WebSocket gateway. This module speaks that transport while
keeping the client's JSON message model: requests and responses are bridged
through protobuf JSON, and failed calls are reported as the same ``error``
objects the WebSocket gateway sends. The client identifies itself honestly; it
never claims to be the official Yandex Music app.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import aiohttp
import grpc
from google.protobuf import json_format
from music_assistant_models.errors import LoginFailed

if TYPE_CHECKING:
    from google.protobuf.message import Message

from .ynison_proto import (
    device_info_header_pb2,
    device_type_pb2,
    redirector_pb2,
    ynison_state_pb2,
)

GRPC_ENDPOINT = "ynison.music.yandex.net:443"
_REDIRECT_METHOD = "/ynison_redirect.YnisonRedirectService/GetRedirectToYnison"
_STATE_METHOD = "/ynison_state.YnisonStateService/PutYnisonState"
_REDIRECT_TIMEOUT = 15.0


class YnisonRejectedError(Exception):
    """Ynison answered a call with an error directive (e.g. a go-away)."""

    def __init__(self, info: dict[str, Any]) -> None:
        """
        Wrap a server error object.

        :param info: Error object in the WebSocket gateway's shape.
        """
        super().__init__(info.get("message", "Ynison rejected the request"))
        self.error_info = info


@dataclass(frozen=True)
class GrpcFrame:
    """One received item, shaped like an aiohttp WebSocket message."""

    type: aiohttp.WSMsgType
    data: str | None = None
    extra: Any = None


def build_metadata(
    token: str,
    device_id: str,
    device_type: str,
    app_name: str,
    app_version: str,
    *,
    accept_language: str,
    redirect_ticket: str | None = None,
    session_id: int | None = None,
) -> list[tuple[str, str]]:
    """
    Return the call metadata for a Ynison gRPC request.

    :param token: Music OAuth token.
    :param device_id: Ynison device id.
    :param device_type: ``DeviceType`` name of this device, e.g. ``WEB``.
    :param app_name: Name of this client application.
    :param app_version: Version of this client application.
    :param accept_language: Preferred content language, e.g. ``ru-RU``.
    :param redirect_ticket: Ticket from the redirector, for the state stream.
    :param session_id: Ynison session id from the redirector, when known.
    """
    header = device_info_header_pb2.YnisonDeviceInfoHeader(
        type=device_type_pb2.DeviceType.Value(device_type),
        app_name=app_name,
        app_version=app_version,
    )
    metadata = [
        ("authorization", f"OAuth {token}"),
        ("ynison-device-id", device_id),
        ("ynison-device-info", base64.b64encode(header.SerializeToString()).decode().rstrip("=")),
        ("accept-language", accept_language),
        ("x-yandex-music-client-now", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("x-yandex-music-content-type", "adult"),
    ]
    if redirect_ticket is not None:
        metadata.append(("ynison-redirect-ticket", redirect_ticket))
    if session_id is not None:
        metadata.append(("ynison-session-id", str(session_id)))
    return metadata


def error_info(err: grpc.aio.AioRpcError) -> dict[str, Any]:
    """Return a failed call as the error object the WebSocket gateway sends."""
    trailers = err.trailing_metadata() or ()
    return {
        "details": {k: v for k, v in trailers if isinstance(v, str) and k.startswith("ynison-")},
        "grpc_code": err.code().value[0],
        "message": err.details() or "",
    }


def to_request(text: str) -> ynison_state_pb2.PutYnisonStateRequest:
    """Return a JSON state request as a protobuf request."""
    request = ynison_state_pb2.PutYnisonStateRequest()
    json_format.Parse(text, request, ignore_unknown_fields=True)
    return request


def to_json(message: Message) -> str:
    """Return a protobuf message as the JSON the WebSocket gateway would send."""
    return json.dumps(
        json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True,
        )
    )


async def redirect(metadata: list[tuple[str, str]]) -> dict[str, Any]:
    """
    Ask the redirector which state host serves this account.

    :param metadata: Call metadata from :func:`build_metadata`.
    :return: Redirect response in the WebSocket gateway's JSON shape.
    :raises LoginFailed: When the token is rejected.
    :raises YnisonRejectedError: When the server answers with another error.
    """
    async with grpc.aio.secure_channel(GRPC_ENDPOINT, grpc.ssl_channel_credentials()) as channel:
        call = channel.unary_unary(
            _REDIRECT_METHOD,
            request_serializer=redirector_pb2.RedirectRequest.SerializeToString,
            response_deserializer=redirector_pb2.RedirectResponse.FromString,
        )
        try:
            response = await call(
                redirector_pb2.RedirectRequest(), metadata=metadata, timeout=_REDIRECT_TIMEOUT
            )
        except grpc.aio.AioRpcError as err:
            if err.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
                raise LoginFailed("Ynison authentication failed — invalid token") from err
            raise YnisonRejectedError(error_info(err)) from err
    result: dict[str, Any] = json.loads(to_json(response))
    return result


class GrpcStateSocket:
    """
    The Ynison state stream presented like an aiohttp WebSocket.

    Text written with :meth:`send_str` is sent as a protobuf request; iterating
    yields each response as a text frame, a server error as a text frame holding
    an ``error`` object, and finally a close frame.
    """

    def __init__(self, host: str, metadata: list[tuple[str, str]], *, keepalive_s: float) -> None:
        """
        Prepare a state stream.

        :param host: State host from the redirector.
        :param metadata: Call metadata including the redirect ticket.
        :param keepalive_s: Keep-alive ping interval in seconds, or 0 for the default.
        """
        self._target = host if ":" in host else f"{host}:443"
        self._metadata = metadata
        self._keepalive_s = keepalive_s
        self._outbox: asyncio.Queue[ynison_state_pb2.PutYnisonStateRequest | None] = asyncio.Queue()
        self._channel: grpc.aio.Channel | None = None
        self._call: Any = None
        self._closed = False
        self.close_code: int | None = None

    @property
    def closed(self) -> bool:
        """Return whether the stream is closed."""
        return self._closed

    async def open(self) -> None:
        """Open the bidirectional state stream."""
        options: list[tuple[str, Any]] = [("grpc.max_receive_message_length", -1)]
        if self._keepalive_s:
            options += [
                ("grpc.keepalive_time_ms", int(self._keepalive_s * 1000)),
                ("grpc.keepalive_permit_without_calls", 1),
            ]
        self._channel = grpc.aio.secure_channel(
            self._target, grpc.ssl_channel_credentials(), options=options
        )
        stream = self._channel.stream_stream(
            _STATE_METHOD,
            request_serializer=ynison_state_pb2.PutYnisonStateRequest.SerializeToString,
            response_deserializer=ynison_state_pb2.PutYnisonStateResponse.FromString,
        )
        self._call = stream(self._requests(), metadata=self._metadata)

    async def send_str(self, text: str) -> None:
        """
        Send one JSON state request.

        :param text: Request in the WebSocket gateway's JSON shape.
        :raises ConnectionError: When the stream is closed.
        """
        if self._closed:
            raise ConnectionError("Ynison gRPC stream is closed")
        await self._outbox.put(to_request(text))

    def exception(self) -> BaseException | None:
        """Return the transport exception; errors are delivered as frames instead."""
        return None

    async def close(self) -> None:
        """Close the stream and its channel."""
        self._closed = True
        await self._outbox.put(None)
        if self._call is not None:
            self._call.cancel()
        if self._channel is not None:
            await self._channel.close()

    def __aiter__(self) -> AsyncIterator[GrpcFrame]:
        """Iterate over received frames until the stream ends."""
        return self._frames()

    async def _frames(self) -> AsyncIterator[GrpcFrame]:
        """Yield responses, then any server error, then a close frame."""
        try:
            async for response in self._call:
                yield GrpcFrame(aiohttp.WSMsgType.TEXT, to_json(response))
        except grpc.aio.AioRpcError as err:
            if err.code() != grpc.StatusCode.CANCELLED:
                yield GrpcFrame(aiohttp.WSMsgType.TEXT, json.dumps({"error": error_info(err)}))
        finally:
            self._closed = True
        yield GrpcFrame(aiohttp.WSMsgType.CLOSE)

    async def _requests(self) -> AsyncIterator[ynison_state_pb2.PutYnisonStateRequest]:
        """Feed queued requests to the call until the stream is closed."""
        while (request := await self._outbox.get()) is not None:
            yield request
