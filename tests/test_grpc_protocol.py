"""Protocol-level tests for the native Ynison gRPC transport."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest
from ya_passport_auth import SecretStr

from provider.grpc_transport import (
    GrpcStateSocket,
    build_metadata,
    redirect,
    to_json,
    to_request,
)
from provider.ynison_client import YnisonClient, YnisonDeviceInfo
from provider.ynison_proto import (
    redirector_pb2,
    ynison_state_pb2,
)

_REQUEST_VARIANTS: dict[str, dict[str, Any]] = {
    "update_full_state": {
        "player_state": {"status": {"paused": True, "progress_ms": "0"}},
        "device": {
            "info": {
                "device_id": "dev",
                "title": "Music Assistant",
                "type": "WEB",
                "app_name": "Music Assistant",
                "app_version": "1",
            },
            "capabilities": {
                "can_be_player": True,
                "can_be_remote_controller": False,
                "volume_granularity": 100,
            },
            "volume_info": {
                "volume": 0.5,
                "version": {"device_id": "dev", "version": "1", "timestamp_ms": "0"},
            },
        },
        "is_currently_active": True,
    },
    "update_active_device": {"device_id_optional": "dev"},
    "update_playing_status": {
        "playing_status": {
            "progress_ms": "1500",
            "duration_ms": "3000",
            "paused": False,
            "playback_speed": 1.0,
        }
    },
    "update_player_state": {"player_state": {"status": {"paused": False}}},
    "update_volume": {"volume": 0.5, "device_id": "dev"},
    "update_player_queue_inject": {
        "player_queue_inject": {
            "playing_status": {"progress_ms": "0"},
            "playable": {
                "playable_id": "shot-1",
                "playable_type": "ALICE_SHOT",
                "title": "Shot",
            },
            "version": {"device_id": "dev", "version": "1"},
        }
    },
    "update_session_params": {"mute_events_if_passive": True},
    "update_volume_info": {
        "device_id": "dev",
        "volume_info": {
            "volume": 0.5,
            "version": {"device_id": "dev", "version": "1"},
        },
    },
    "sync_state_from_eov": {"actual_queue_id": "queue-1"},
}


@pytest.mark.parametrize("variant", sorted(_REQUEST_VARIANTS))
def test_every_put_ynison_state_variant_round_trips(variant: str) -> None:
    """Every oneof branch defined by the official schema survives the JSON bridge."""
    request = to_request(
        json.dumps(
            {
                variant: _REQUEST_VARIANTS[variant],
                "rid": "request-id",
                "player_action_timestamp_ms": "123",
            }
        )
    )

    assert request.WhichOneof("parameters") == variant
    assert request.rid == "request-id"
    assert request.player_action_timestamp_ms == 123


def test_full_state_keeps_device_volume_and_capabilities() -> None:
    """The registration device carries capabilities and the new volume message."""
    request = to_request(
        json.dumps(
            {
                "update_full_state": _REQUEST_VARIANTS["update_full_state"],
                "rid": "r",
                "player_action_timestamp_ms": "1",
            }
        )
    )

    device = request.update_full_state.device
    assert device.capabilities.volume_granularity == 100
    assert device.volume_info.volume == 0.5
    assert device.info.app_name == "Music Assistant"
    assert request.update_full_state.is_currently_active is True


def test_response_exposes_devices_session_and_volume() -> None:
    """The response bridge preserves the device list, session and volume."""
    response = ynison_state_pb2.PutYnisonStateResponse()
    device = response.devices.add()
    device.info.device_id = "dev"
    device.info.title = "Music Assistant"
    device.session.id = 42
    device.volume_info.volume = 0.25
    response.active_device_id_optional.value = "dev"
    response.timestamp_ms = 99

    data = json.loads(to_json(response))

    assert data["devices"][0]["info"]["device_id"] == "dev"
    assert data["devices"][0]["session"]["id"] == "42"
    assert data["devices"][0]["volume_info"]["volume"] == 0.25
    assert data["active_device_id_optional"] == "dev"
    assert data["timestamp_ms"] == "99"


def _client() -> tuple[YnisonClient, AsyncMock]:
    socket = AsyncMock()
    socket.closed = False
    client = YnisonClient(
        token=SecretStr("token"),
        device_info=YnisonDeviceInfo(device_id="dev", title="Music Assistant"),
        on_state_update=AsyncMock(),
        logger=MagicMock(),
    )
    client._ws = socket
    client._connected = True
    return client, socket


async def test_client_volume_update_sends_update_volume_info() -> None:
    """The client sends UpdateVolumeInfo with a version authored by this device."""
    client, socket = _client()

    assert await client.update_volume_info(42) is True

    message = json.loads(socket.send_str.await_args.args[0])
    volume_info = message["update_volume_info"]
    assert volume_info["device_id"] == "dev"
    assert volume_info["volume_info"]["volume"] == 0.42
    assert volume_info["volume_info"]["version"]["device_id"] == "dev"
    assert client.volume == 42


async def test_full_state_carries_active_flag_interception_and_eov() -> None:
    """Full state advertises activity, interception and an embedded EOV request."""
    client, socket = _client()

    await client.send_full_state(
        is_currently_active=True,
        intercept_if_no_one_active=True,
        sync_eov_queue_id="queue-1",
    )

    message = json.loads(socket.send_str.await_args.args[0])
    full_state = message["update_full_state"]
    assert full_state["is_currently_active"] is True
    assert full_state["sync_state_from_eov_optional"]["actual_queue_id"] == "queue-1"
    assert full_state["device"]["volume_info"]["volume"] == 0.0
    assert message["activity_interception_type"] == "INTERCEPT_IF_NO_ONE_ACTIVE"
    assert to_request(json.dumps(message)).WhichOneof("parameters") == "update_full_state"


async def test_fake_grpc_server_receives_metadata_and_state() -> None:
    """Real gRPC framing and metadata reach both Ynison methods."""
    redirect_metadata: dict[str, str] = {}
    state_metadata: dict[str, str] = {}
    state_requests: list[ynison_state_pb2.PutYnisonStateRequest] = []
    port_holder: dict[str, int] = {}

    async def redirect_handler(
        _request: redirector_pb2.RedirectRequest, context: grpc.aio.ServicerContext
    ) -> redirector_pb2.RedirectResponse:
        redirect_metadata.update(dict(context.invocation_metadata()))
        port = port_holder["port"]
        return redirector_pb2.RedirectResponse(
            host=f"127.0.0.1:{port}",
            redirect_ticket="ticket",
            session_id=42,
            keep_alive_params=redirector_pb2.KeepAliveParams(keep_alive_time_seconds=20),
        )

    async def state_handler(requests: Any, context: grpc.aio.ServicerContext) -> Any:
        state_metadata.update(dict(context.invocation_metadata()))
        async for request in requests:
            state_requests.append(request)
            if request.WhichOneof("parameters") == "update_full_state":
                response = ynison_state_pb2.PutYnisonStateResponse()
                response.active_device_id_optional.value = "dev"
                response.timestamp_ms = 7
                yield response

    handler = grpc.method_handlers_generic_handler(
        "ynison_redirect.YnisonRedirectService",
        {
            "GetRedirectToYnison": grpc.unary_unary_rpc_method_handler(
                redirect_handler,
                request_deserializer=redirector_pb2.RedirectRequest.FromString,
                response_serializer=redirector_pb2.RedirectResponse.SerializeToString,
            )
        },
    )
    state_handler_obj = grpc.method_handlers_generic_handler(
        "ynison_state.YnisonStateService",
        {
            "PutYnisonState": grpc.stream_stream_rpc_method_handler(
                state_handler,
                request_deserializer=ynison_state_pb2.PutYnisonStateRequest.FromString,
                response_serializer=ynison_state_pb2.PutYnisonStateResponse.SerializeToString,
            )
        },
    )
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((handler, state_handler_obj))
    port = server.add_insecure_port("127.0.0.1:0")
    port_holder["port"] = port
    await server.start()
    metadata = build_metadata("token", "dev", "WEB", "Music Assistant", "1", accept_language="en")
    try:
        redirect_response = await redirect(metadata, target=f"127.0.0.1:{port}", secure=False)
        assert redirect_response["host"] == f"127.0.0.1:{port}"
        assert redirect_response["redirect_ticket"] == "ticket"

        state_call_metadata = build_metadata(
            "token",
            "dev",
            "WEB",
            "Music Assistant",
            "1",
            accept_language="en",
            redirect_ticket="ticket",
            session_id=42,
        )
        socket = GrpcStateSocket(
            redirect_response["host"], state_call_metadata, keepalive_s=0, secure=False
        )
        await socket.open()
        await socket.send_str(
            json.dumps(
                {
                    "update_full_state": _REQUEST_VARIANTS["update_full_state"],
                    "rid": "r",
                    "player_action_timestamp_ms": "1",
                }
            )
        )
        frame = await anext(socket.__aiter__())
        await socket.close()

        assert json.loads(frame.data or "")["active_device_id_optional"] == "dev"
        assert redirect_metadata["ynison-device-id"] == "dev"
        assert state_metadata["ynison-redirect-ticket"] == "ticket"
        assert state_metadata["ynison-session-id"] == "42"
        assert state_requests[0].WhichOneof("parameters") == "update_full_state"
        assert state_requests[0].update_full_state.is_currently_active is True
    finally:
        await server.stop(0)


async def test_client_adopts_server_volume_and_session() -> None:
    """A response exposes our device session and volume through the client."""
    client, _socket = _client()

    client._parse_state(
        {
            "devices": [
                {
                    "info": {"device_id": "dev"},
                    "session": {"id": "42"},
                    "volume_info": {"volume": 0.25},
                }
            ],
            "active_device_id_optional": "dev",
        }
    )

    assert client.volume == 25
    assert client.session_id == 42


async def test_queue_inject_builds_the_protocol_message() -> None:
    """The injected entity request is a valid PutYnisonState oneof branch."""
    client, socket = _client()

    sent = await client.update_player_queue_inject(
        {"progress_ms": "0", "paused": False},
        {"playable_id": "ad-1", "playable_type": "AD", "title": "Ad"},
    )

    assert sent is True
    message = json.loads(socket.send_str.await_args.args[0])
    request = to_request(json.dumps(message))
    assert request.WhichOneof("parameters") == "update_player_queue_inject"
    assert request.update_player_queue_inject.player_queue_inject.playable.playable_id == "ad-1"


def test_wave_queue_fields_survive_the_bridge() -> None:
    """New queue oneof and per-playable analytics fields are not normalized away."""
    request = to_request(
        json.dumps(
            {
                "update_player_state": {
                    "player_state": {
                        "player_queue": {
                            "current_playable_index": 1,
                            "playable_list": [
                                {"playable_id": "a"},
                                {
                                    "playable_id": "b",
                                    "track_info": {"batch_id_optional": "batch-1"},
                                },
                            ],
                            "queue": {
                                "wave_queue": {
                                    "recommended_playable_list": [
                                        {
                                            "playable_id": "c",
                                            "track_info": {"batch_id_optional": "b2"},
                                        }
                                    ],
                                    "live_playable_index": 1,
                                    "navigation_id_optional": "nav-1",
                                    "playback_action_id_optional": "action-1",
                                }
                            },
                        }
                    }
                },
                "rid": "r",
            }
        )
    )

    queue = request.update_player_state.player_state.player_queue
    assert queue.queue.WhichOneof("type") == "wave_queue"
    wave = queue.queue.wave_queue
    assert wave.live_playable_index == 1
    assert wave.recommended_playable_list[0].playable_id == "c"
    assert wave.recommended_playable_list[0].track_info.batch_id_optional.value == "b2"
    assert wave.navigation_id_optional.value == "nav-1"
    assert queue.playable_list[1].track_info.batch_id_optional.value == "batch-1"
