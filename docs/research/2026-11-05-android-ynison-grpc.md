# Yandex Music Android: native Ynison gRPC research

Date: 2026-11-05.
Device: Pixel 8, Android 17 (SDK 37), USB debugging.
Application: `ru.yandex.music`, version `2026.09.5 #167.1gpr`
(versionCode `24026502`), installed 2026-10-28.

## Method

- Pulled the base APK and the arm64, en, ru and xxhdpi splits with `adb`.
- Extracted the `.proto` sources that the application ships in the APK root.
- Disassembled all six DEX files with baksmali and decompiled them with jadx.
- Read the generated gRPC stubs, metadata interceptors, request builders and
  retry manager.
- Inspected the device at runtime: device selector, current TCP connections,
  logcat and the vendor services used for playback.

The application is R8-obfuscated, so class names below are the surviving
protocol names; helper classes are referenced by their role.

## Shipped schema

The APK ships the full Ynison schema, not only the subset used by the old
WebSocket client:

| File | Service / main messages |
|---|---|
| `redirector/ynison-redirector-service.proto` | `ynison_redirect.YnisonRedirectService.GetRedirectToYnison`, `RedirectResponse`, `KeepAliveParams` |
| `ynisonstate/ynison_state.proto` | `ynison_state.YnisonStateService.PutYnisonState` (bidi), all `Update*` request variants and `PutYnisonStateResponse` |
| `ynisonstate/device.proto` | `Device`, `DeviceInfo`, `DeviceCapabilities`, `DeviceVolume`, `Session` |
| `ynisonstate/queue.proto` | `PlayerQueue`, `Queue` oneof (`WaveQueue`, generative, FM radio, video wave, local tracks), shuffle and entity options |
| `ynisonstate/playable.proto` | `Playable`, `TrackInfo`, `VideoClipInfo` |
| `ynisonstate/playing_status.proto` | `PlayingStatus` |
| `ynisonstate/update_version.proto` | `UpdateVersion` |
| `ynisonstate/device_info_header.proto` | `YnisonDeviceInfoHeader` |
| `relay/*.proto` | local `relay.RelayGrpcService` |

`PutYnisonStateRequest` has these oneof branches:
`update_full_state` (1), `update_active_device` (2), `update_playing_status`
(3), `update_player_state` (4), deprecated `update_volume` (5),
`update_player_queue_inject` (6), `update_session_params` (9),
`update_volume_info` (11), `sync_state_from_eov` (12). Every request carries
`player_action_timestamp_ms` (7), `rid` (8) and `activity_interception_type`
(10).

`PutYnisonStateResponse` carries `player_state`, repeated `devices`,
`active_device_id_optional`, `timestamp_ms` and `rid`.

## Transport and metadata

- Target: `ynison.music.yandex.net:443`.
- gRPC-Java over OkHttp (`grpc-java-okhttp/1.61.1`).
- `Ynison-Device-Info` is a base64 (standard alphabet, no padding, no line
  breaks) serialized `YnisonDeviceInfoHeader(type, app_name, app_version)`.
- Redirect call metadata: `Ynison-Session-Id`, `Ynison-Device-Id`,
  `Ynison-Device-Info`.
- State stream metadata adds `Ynison-Redirect-Ticket`.
- The official app advertises `app_name = "Yandex Music"`, the installed
  version and `DeviceType.ANDROID` (enum value 2). A Music Assistant device
  stays honest and uses `WEB`.

## Registration shape

`UpdateDevice` is built from the device provider:

- `info`: device id, title (`Build.MANUFACTURER + " " + Build.MODEL`),
  `DeviceType`, app name, app version.
- `capabilities`: `can_be_player = true`, `can_be_remote_controller = true`,
  `volume_granularity = AudioManager.getStreamMaxVolume(...)`.
- deprecated `volume` plus `volume_info = DeviceVolume(volume, version)`.
- `UpdateFullState` adds `is_currently_active` and an optional
  `sync_state_from_eov` request. The player queue is trimmed to 200 items and
  the queue version timestamp is zeroed when the queue has no version.

`UpdateActiveDevice` carries only the optional device id and no interception
mode.

## Volume

- Current request: `UpdateVolumeInfo(device_id, DeviceVolume(volume, version))`.
  Volume is `[0.0, 1.0]`, rounded to four decimals in the service contract and
  clamped by the client when its request validator is enabled.
- Deprecated `UpdateVolume` is not sent by this application.
- `UpdateDevice` carries both the deprecated scalar and `volume_info`.
- `DeviceCapabilities.volume_granularity` advertises the slider step count.

## Interception and command gating

- `DO_NOT_INTERCEPT_BY_DEFAULT`, `INTERCEPT_IF_NO_ONE_ACTIVE`,
  `INTERCEPT_EAGER` are the three values.
- Full state uses `INTERCEPT_IF_NO_ONE_ACTIVE` when the client wants to capture
  activity if no other device is online.
- Playing status and player state derive the mode from the current status; a
  passive device is not allowed to send ordinary commands unless it is
  intercepting.
- A redirect rejection is applied through the same retry policy as a state
  rejection.

## Reconnect policy

The surviving `RetryManager` configuration:

- default back-off ladder: `1000`, `5000`, `30000` ms;
- response headers: `Ynison-Backoff-Millis`,
  `Ynison-Go-Away-For-Seconds`, `Ynison-Error-Code`;
- retryable gRPC statuses: `UNAVAILABLE` (14), `ABORTED` (10),
  `RESOURCE_EXHAUSTED` (8);
- a go-away ends the session and delays the next dial by the exact window;
- an exhausted ladder waits for an external trigger (network, foreground,
  account state). A long-running plugin has no such trigger and keeps retrying
  at a slow idle interval instead.

This matches the implemented `ReconnectPolicy`.

## Queue model

- `PlayerQueue.playable_list` is the original-order list.
- `shuffle_optional.playable_indices` is the playback permutation.
- The new `queue` oneof adds `WaveQueue.recommended_playable_list`,
  `live_playable_index`, `entity_options` (rotor session and track sources),
  queue-level navigation/playback ids and per-playable `TrackInfo.batch_id`.
- `PlayerQueue` also keeps deprecated flat fields for older clients.
- Queue edit commands used by the app are marker commands:
  `AddNext`, `AddLast`, `RemoveAt`, `Move`, `Next`, `Back`, `QueuePosition`,
  `OriginalPosition`, `RepeatToggle`, `ShuffleToggle`, `ShuffleWithIndices`,
  `ReverseToggle`. They are serialized as an `UpdatePlayerState` carrying the
  edited queue; there is no separate gRPC queue-edit method.

## Relay

The APK contains a local `relay.RelayGrpcService` with `Version`,
`CheckAuthorization`, server-streaming `StreamStateUpdates` and
`InvokeCommand`. The application runs it as an Android bound service with
certificate pinning. It is the local playback relay used by companion clients,
not the remote Ynison device protocol, so it is out of scope for this provider.

## Runtime observations

- The device selector showed `This phone`, `Yandex mini 2 007 a` and
  `Yandex Music on Kinopoisk`.
- While controlling the Station, the app held connections to
  `iot.quasar.yandex.ru`, `quasar.yandex.net`, `api.music.yandex.net`,
  `avatars.mds.yandex.net`, the stream CDN and the Station on local port 1961.
  It did not connect to the Ynison host in this single-account scenario.
- Release logcat does not expose Ynison or gRPC logs, so dynamic wire capture
  was not possible without TLS interception. The local Station path uses the
  Quasar/IoT services rather than Ynison.

## Live Ynison check

A redirect call with a valid linked Music Assistant token and a real device id
returned:

```json
{
  "details": {
    "ynison-error-code": "500140000",
    "ynison-go-away-for-seconds": "43200"
  },
  "grpc_code": 14,
  "message": "Ynison service is temporary unavailable."
}
```

The same account and IP are rejected over WebSocket. The native gRPC transport
therefore does **not** bypass the current service-side block; the returned
window is 12 hours. The transport must honour that window and not retry inside
it. Live end-to-end verification remains an external blocker until Yandex
accepts the account again; local gRPC tests cover framing and the full message
surface in the meantime.

## Consequences for the provider

- Official schema replaces hand-maintained field assumptions.
- Device registration must include capabilities and volume; volume must be
  sent with `UpdateVolumeInfo`.
- Full state must be able to report activity and request interception.
- Responses must expose the device list and session, not only the active device.
- Queue edits are `UpdatePlayerState` mutations; the client keeps the current
  item and shuffle order stable across them.
- The relay service is not part of the Ynison device contract.
