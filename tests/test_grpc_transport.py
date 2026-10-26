"""Tests for the experimental Ynison gRPC transport."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
import grpc
import pytest
from music_assistant_models.errors import LoginFailed

from provider.grpc_transport import (
    GrpcStateSocket,
    YnisonRejectedError,
    build_metadata,
    error_info,
    redirect,
    to_json,
    to_request,
)
from provider.ynison_proto import device_info_header_pb2, device_type_pb2, ynison_state_pb2


def _rpc_error(code: grpc.StatusCode, trailers: tuple[tuple[str, str], ...] = ()) -> Exception:
    return grpc.aio.AioRpcError(  # type: ignore[no-any-return]
        code, grpc.aio.Metadata(), grpc.aio.Metadata(*trailers), details="denied"
    )


def _md(metadata: list[tuple[str, str]]) -> dict[str, str]:
    return dict(metadata)


def test_metadata_identifies_the_client_honestly() -> None:
    """The device header names Music Assistant; nothing claims to be the official app."""
    md = _md(
        build_metadata("tok", "dev-1", "WEB", "Music Assistant", "4.4.1", accept_language="ru-RU")
    )

    header = device_info_header_pb2.YnisonDeviceInfoHeader.FromString(
        base64.b64decode(md["ynison-device-info"] + "==")
    )
    assert header.type == device_type_pb2.WEB
    assert header.app_name == "Music Assistant"
    assert header.app_version == "4.4.1"
    assert "=" not in md["ynison-device-info"]
    assert md["authorization"] == "OAuth tok"
    assert md["ynison-device-id"] == "dev-1"
    assert md["accept-language"] == "ru-RU"
    assert md["x-yandex-music-content-type"] == "adult"
    assert datetime.fromisoformat(md["x-yandex-music-client-now"]).tzinfo is not None
    assert "x-yandex-music-client" not in md
    assert "user-agent" not in md


def test_state_metadata_carries_ticket_and_session() -> None:
    """The state stream presents the redirect ticket and session id."""
    md = _md(
        build_metadata(
            "tok", "d", "WEB", "MA", "1", accept_language="en", redirect_ticket="t", session_id=7
        )
    )

    assert md["ynison-redirect-ticket"] == "t"
    assert md["ynison-session-id"] == "7"


def test_request_and_response_keep_default_values() -> None:
    """Proto3 defaults (False, 0) survive the JSON bridge both ways."""
    request = to_request(
        json.dumps(
            {
                "update_playing_status": {
                    "playing_status": {
                        "progress_ms": "0",
                        "duration_ms": "1000",
                        "paused": False,
                        "playback_speed": 1.0,
                    }
                },
                "rid": "r",
                "player_action_timestamp_ms": "5",
                "activity_interception_type": "INTERCEPT_IF_NO_ONE_ACTIVE",
            }
        )
    )
    assert request.WhichOneof("parameters") == "update_playing_status"

    response = ynison_state_pb2.PutYnisonStateResponse()
    response.player_state.status.paused = False
    response.player_state.player_queue.current_playable_index = 0
    response.active_device_id_optional.value = "dev-1"
    data = json.loads(to_json(response))

    status = data["player_state"]["status"]
    assert status["paused"] is False
    assert data["player_state"]["player_queue"]["current_playable_index"] == 0
    assert data["active_device_id_optional"] == "dev-1"
    assert isinstance(status["progress_ms"], str)


def test_error_info_matches_websocket_error_frames() -> None:
    """GRPC trailers become the same error object the WebSocket gateway sends."""
    err = _rpc_error(
        grpc.StatusCode.UNAVAILABLE,
        (("ynison-error-code", "500140000"), ("ynison-go-away-for-seconds", "43200")),
    )

    assert error_info(err) == {
        "details": {"ynison-error-code": "500140000", "ynison-go-away-for-seconds": "43200"},
        "grpc_code": 14,
        "message": "denied",
    }


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (grpc.StatusCode.UNAUTHENTICATED, LoginFailed),
        (grpc.StatusCode.UNAVAILABLE, YnisonRejectedError),
    ],
)
async def test_redirect_maps_rejections(code: grpc.StatusCode, expected: type[Exception]) -> None:
    """An auth rejection is LoginFailed; any other server answer carries its directive."""
    channel = MagicMock()
    channel.__aenter__.return_value = channel
    channel.unary_unary.return_value = MagicMock(side_effect=_rpc_error(code))

    with (
        patch("provider.grpc_transport.grpc.aio.secure_channel", return_value=channel),
        pytest.raises(expected),
    ):
        await redirect([("authorization", "OAuth t")])


class _FakeCall:
    """A bidirectional call that yields responses, then optionally fails."""

    def __init__(self, responses: list[Any], error: Exception | None, requests: Any) -> None:
        self._responses = responses
        self._error = error
        self.requests = requests
        self.cancelled = False

    def __aiter__(self) -> Any:
        async def gen() -> Any:
            for response in self._responses:
                yield response
            if self._error:
                raise self._error

        return gen()

    def cancel(self) -> bool:
        self.cancelled = True
        return True


async def test_state_socket_yields_frames_like_a_websocket() -> None:
    """State responses, then the server error, then a close are delivered as frames."""
    response = ynison_state_pb2.PutYnisonStateResponse()
    response.active_device_id_optional.value = "dev-1"
    calls: list[_FakeCall] = []

    def stream_stream(*_args: Any, **_kwargs: Any) -> Any:
        def invoke(requests: Any, **_kwargs: Any) -> _FakeCall:
            call = _FakeCall(
                [response],
                _rpc_error(grpc.StatusCode.UNAVAILABLE, (("ynison-error-code", "500140000"),)),
                requests,
            )
            calls.append(call)
            return call

        return invoke

    channel = MagicMock()
    channel.stream_stream.side_effect = stream_stream
    channel.close = MagicMock(return_value=asyncio.sleep(0))
    with patch("provider.grpc_transport.grpc.aio.secure_channel", return_value=channel):
        socket = GrpcStateSocket("host.example", [("a", "b")], keepalive_s=20)
        await socket.open()
        frames = [frame async for frame in socket]

    assert [f.type for f in frames] == [
        aiohttp.WSMsgType.TEXT,
        aiohttp.WSMsgType.TEXT,
        aiohttp.WSMsgType.CLOSE,
    ]
    assert json.loads(frames[0].data or "")["active_device_id_optional"] == "dev-1"
    assert json.loads(frames[1].data or "")["error"]["details"]["ynison-error-code"] == "500140000"
    assert socket.closed


async def test_state_socket_sends_parsed_requests() -> None:
    """Messages written to the socket reach the request stream as protobuf requests."""
    captured: dict[str, Any] = {}

    def stream_stream(*_args: Any, **_kwargs: Any) -> Any:
        def invoke(requests: Any, **_kwargs: Any) -> _FakeCall:
            captured["requests"] = requests
            return _FakeCall([], None, requests)

        return invoke

    channel = MagicMock()
    channel.stream_stream.side_effect = stream_stream
    channel.close = MagicMock(return_value=asyncio.sleep(0))
    with patch("provider.grpc_transport.grpc.aio.secure_channel", return_value=channel):
        socket = GrpcStateSocket("host.example", [], keepalive_s=0)
        await socket.open()
        await socket.send_str(
            json.dumps({"update_session_params": {"mute_events_if_passive": True}})
        )
        first = await anext(captured["requests"])
        await socket.close()

    assert first.update_session_params.mute_events_if_passive is True
    assert socket.closed
