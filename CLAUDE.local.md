# CLAUDE.md — Yandex Music Connect (Ynison)

## Project overview

This repository contains the stable Music Assistant plugin that publishes a
Music Assistant player as a device in the Yandex Music app.

- **Provider base:** `PluginProvider`
- **Feature:** `ProviderFeature.AUDIO_SOURCE`
- **Manifest:** `type=plugin`, `stage=stable`, `multi_instance=true`
- **Domain:** `yandex_ynison`
- **Dependency:** one explicitly linked `yandex_music` provider per instance
- **Source contract:** one exclusive first-class `AudioSource` (`main`)

## Architecture

```text
Yandex Music clients
  │
  ▼
YnisonClient
  ├─ redirector handshake
  ├─ state-service WebSocket
  ├─ state parsing and echo classification
  └─ reconnect and token-refresh callback
  │
  ▼
YandexYnisonProvider
  ├─ setup-owned linked account and concrete player
  ├─ player-owned AudioSource session
  ├─ Ynison ↔ Music Assistant controls and progress
  ├─ linked yandex_music StreamDetails/audio generator
  └─ RADIO queue replenishment
  │
  ▼
per-track ffmpeg → session-fixed PCM → Music Assistant player
```

## Architectural invariants

- **Linked credentials only.** `ym_instance` is required. Legacy `__own__`,
  QR login, manually persisted Ynison tokens, and session ownership by this
  provider are removed.
- **Single credential owner.** Yandex Music owns persistent `token` and
  `x_token` values. Ynison reads them through `get_setup_value` and never
  writes them back.
- **Player-owned exclusivity.** `on_source_selected` claims the source in
  `PlaybackSession` (owner, consumer, stream session id); the session id rejects
  teardown callbacks from superseded requests on the same player.
- **Side-effect-free stream details.** `get_stream_details(item_id,
  media_type)` does not claim playback ownership, so preload cannot reserve the
  source.
- **Session-frozen PCM.** `get_audio_stream` snapshots
  `_normalized_params`; a format change applies to the next session.
- **Fresh formats.** Every boundary receives a new mutable `AudioFormat`
  instance because Music Assistant ffmpeg processing mutates it.
- **One pacing authority.** Per-track ffmpeg decodes without `-re`; Music
  Assistant owns realtime pacing and backpressure bounds read-ahead.
- **Clamped progress.** Never send `progress_ms > duration_ms`; Ynison rejects
  it and tears down the WebSocket.
- **Causal echo detection.** Fully authored state remains an echo; empty-version
  status responses are echoes only when they match a recent successful outbound
  status and any attached queue is unchanged. Authoritative peer state always wins.
- **Reconnect settling.** Fresh empty/paused state is sent after reconnect and
  provider actions are suppressed for two seconds while retained state settles.
- **Radio exception.** Normal queues are controlled by Yandex. For `RADIO`
  entities the active device fetches and appends rotor tracks near queue end.
- **Logical queue order.** `current_playable_index` addresses the original
  playable list; `shuffle_optional.playable_indices` defines playback order.
  Metadata, streaming, navigation, prefetch, repeat, and edits use that same order.

## Module map

| File | Responsibility |
|------|----------------|
| `provider/__init__.py` | Provider setup entry point and supported features |
| `provider/setup_flow.py` | Linked account and required target-player setup/reconfigure |
| `provider/credential_source.py` | Provider-local adapter for setup-owned Yandex Music credentials |
| `provider/auth.py` | Temporary music-token refresh from an `x_token` |
| `provider/provider.py` | AudioSource lifecycle, streaming, control sync, metadata, and RADIO replenishment |
| `provider/playback_session.py` | Source claim, stream cursor, restart and stop requests with reasons, echo grace window |
| `provider/reconnect_policy.py` | Pure reconnect timing: ladders, go-away, retryable statuses, idle retry |
| `provider/queue_model.py` | Pure queue view and edits: navigation, index moves, appends with the 200-item window, repeat, shuffle |
| `provider/ynison_client.py` | Ynison transport, state parsing, echo/relay classification, status reporter, queue commands, strict sends |
| `provider/streaming.py` | PCM profiles, probe arguments, and fresh format factory |
| `provider/protocols.py` | Structural subset required from `yandex_music` |
| `provider/constants.py` | URLs, keys, defaults, timeouts, and protocol errors |
| `provider/strings.json` | Setup/runtime UI labels and descriptions |
| `provider/manifest.json` | Music Assistant provider metadata and runtime requirement |

## Configuration ownership

### Setup-owned values

The native setup flow stores these values in setup data:

| Key | Meaning |
|-----|---------|
| `ym_instance` | Required linked Yandex Music provider instance |
| `mass_player_id` | Required concrete target player; its current name is advertised |

With one Yandex Music instance, setup selects it automatically. With several,
the user must choose. No configured Yandex Music provider aborts setup with
`missing_dependency`; no available player aborts with `no_players`. Reconfigure
clears legacy auth keys rather than transferring credentials. Core migration
(`migrate_connected_player_plugins`) clears legacy `__auto__` players and
`publish_name`; the provider only sees an empty player and fails with
`no_connected_player` until a concrete player is selected.

### Runtime values

| Key | Default | Meaning |
|-----|---------|---------|
| `allow_player_switch` | `true` | Allow this source to move to another player |
| `output_sample_rate` | `auto` | `auto`, 44100, 48000, or 96000 Hz |
| `output_bit_depth` | `auto` | `auto`, 16, or 24 bit |
| `device_id` | generated | Hidden persistent 16-character Ynison device id |

## Credential lifecycle

`YandexMusicCredentialSource.read_tokens()` resolves the exact linked
provider, verifies its domain/type, and reads setup-owned `token` and
`x_token` values. A missing linked provider is temporary during startup; an
incompatible provider or unsupported setup API is a login failure.

This Music Assistant-specific adapter intentionally remains inside the
provider. It owns no Passport authentication behavior: it never refreshes,
rotates, or persists credentials, and it does not depend on the shared
credential-source abstraction from `ya-passport-auth.ma`. Yandex Music remains
the sole persistent credential owner.

A stored music token is preferred. If only `x_token` is available,
`_refresh_via_x_token` mints a temporary music token and caches it in memory
for 50 minutes. The four-entry cache uses SHA-256 hashes of `x_token` values
as keys and coalesces concurrent refreshes with a lock. A Ynison 401/403
invalidates the rejected token path and refreshes before the next reconnect
attempt. No secret is logged or persisted by Ynison.

## Streaming and format selection

No-hint auto profiles are:

- lossy: 16-bit/44.1kHz, stereo PCM S16LE;
- lossless: 24-bit/44.1kHz, stereo PCM S24LE.

`_prefetch_format_for_track` has a 2.5-second best-effort budget. A valid real
stream hint may promote rate/depth, including 96 kHz. Explicit configuration
wins over hints. Automatic rates are snapped down to the nearest supported
target-player rate; explicit rates are preserved.

PCM remains fixed across every track in one source session. The dynamic mode
and its coordinator have been removed. Old `stream_mode` settings are ignored;
they cannot affect setup, format selection, or playback.

`get_audio_stream` follows Ynison track changes in one long-lived AudioSource
session. It fetches cached StreamDetails, runs one ffmpeg decoder per track,
updates metadata/duration, counts PCM bytes for progress, aligns interrupted
output to a complete frame, signals natural completion, and waits for Ynison to
confirm the next track.

## Playback and session ownership

`on_source_selected` records the owning player, physical consumer, and playback
session id. Switching
players stops the previous player. When switching is disabled, a wrong-player
selection is rejected and redirected at most once per idempotency window.

An external Ynison pause stops the Music Assistant source so the UI reaches
IDLE; resume reissues `play_media` from Ynison progress. Seek restarts the
local track generator at the requested offset. Natural end, pause, track
change, and stale session teardown are classified separately so an interrupted
track is never advanced accidentally.

## Ynison transport and recovery

The transport performs:

1. redirector WebSocket authentication;
2. ticket/session extraction;
3. state-service WebSocket authentication;
4. fresh device/full-state registration;
5. passive-event muting request;
6. message-loop state dispatch.

Reconnect timing lives in `ReconnectPolicy` and follows the official client:
1, 5 and 30 second delays without jitter, or the server's `ynison-backoff-millis`
ladder; a `ynison-go-away-for-seconds` response ends the session and holds the
next dial for exactly that window (within one process; it is not persisted).
The ladder restarts when the error kind changes (server code vs. transport) and
after the first healthy state message. An exhausted ladder, or a gRPC status the
official client does not retry (anything but 8/10/14), waits 300 seconds. The
redirector's `keep_alive_params` set the WebSocket heartbeat (at least 5 s).
Only one reconnect task may exist. Strict
sends raise `YnisonSendError` for user commands and delivery-critical queue
updates after waiting up to five seconds for a reconnecting channel; progress
and prefetch publications remain best-effort. `report_status` publishes progress
only when it differs from the newest server-known status (received or sent) by
more than two seconds, a pause change, or a new duration, and skips best-effort
reports while another device is active.
An empty redirect ticket is a `LoginFailed`, like 401/403. During reconnect,
these failures share a one-attempt credential-refresh budget. Unexpected
parser/callback errors propagate after socket cleanup and reconnect scheduling.

## Radio queues

Repeat, shuffle, queue advance, and RADIO replenishment use one serialized
queue mutation path. A successful send supplies the next mutation's queue base
until its echo, peer replacement, disconnect/reconnect, or a 30-second timeout.
Older own queue versions cannot overwrite a newer sent version. Server state
remains authoritative; pending queue edits do not optimistically change status.
Next/previous and terminal repeat/stop decisions use the mutation's queue base
under the send lock. A navigation lock also orders RADIO fetches. Peer queue
replacements or active-device changes invalidate queued mutations (a peer
repeat/shuffle edit only replaces the queue base); unchanged peer heartbeats do
not discard unacknowledged commands. RADIO API results and prefetch caches carry
their originating queue generation and are discarded after replacement.
Outgoing add/remove/move helpers are deferred until MA exposes an AudioSource API
for those controls. Incoming peer queue edits remain supported.

Natural completion waits at most ten seconds for transport recovery and retries
one failed queue publication. A changed queue, active device, or pause state
invalidates the pending completion. RADIO decisions can return `False` from
the mutation callback to fetch tracks without sending unchanged state.

When a `RADIO` queue reaches its final two items, the provider prefetches
rotor tracks through the linked Yandex Music provider. It maps returned tracks
to Ynison queue items and publishes the expanded list. At natural track end it
uses prefetched data when available, otherwise fetches synchronously, advances
the queue version/index, and waits for a different track id or queue position.
Shuffle mappings are extended with the new original indices. Repeat ONE restarts
the current item; repeat ALL wraps finite queues; repeat NONE stops at their end.

## Concurrency and ownership

Each rule names the test that enforces it.

- **State is applied one frame at a time.** The client parses a frame and awaits
  the provider's state callback before reading the next one, so state cannot
  change while a callback awaits (for example the 2.5 s format prefetch). Do not
  move the callback into a separate task without re-checking state after every
  await. Test: `test_state_frames_wait_for_the_previous_callback`.
- **Every background task has an owner.** The provider starts tasks only through
  `_spawn`; `unload` cancels and awaits them, letting source releases handed to
  Music Assistant finish for up to five seconds. The client owns its message and
  reconnect tasks and stops them in `disconnect`. Tests:
  `tests/standalone/test_task_ownership.py`, `test_unload_cancels_every_spawned_task`,
  `test_unload_lets_source_release_finish`.
- **Lock order.** `_queue_navigation_lock` (provider) is taken before the client's
  `_send_lock`; `_token_refresh_lock` is a leaf taken alone. Never call into the
  provider while holding `_send_lock`.

### Shadow state

| Copy | Source of truth | Goes stale when | Re-checked |
|------|-----------------|-----------------|------------|
| `PlaybackSession` claim (owner, session id) | MA streams controller callbacks | a same-owner reconnect supersedes the request | `lost(token)` in the stream loop and its `finally` |
| `PlaybackSession.track_id` / `index` | Ynison queue | a peer queue edit or our window trim | track-change detection; the client flags our own echoes as item-keeping (`current_item_kept`) or navigation (`current_item_navigated`) |
| `PlaybackSession.progress_ms` | PCM bytes streamed | seek or restart | reset at each item start; `position_ms` prefers a pending start, else the client's `estimated_progress_ms` |
| Client pending queue base | our last sent queue | echo, peer replacement, reconnect, 30 s | `queue_snapshot()`; queue epoch |
| Client `StatusBaseline` | newest status received or sent | track change | `report_status` dedup; `status_is_relay` |
| Navigation baseline | queue lineage, current item, our navigation version | a foreign queue other than a repeat/shuffle edit (lineage) or the confirmed echo | `is_current_playback`; `navigation_confirmed` |
| RADIO prefetch cache | rotor API for one queue generation | peer queue replacement | generation check before use |

### Review checklist

- Reconnect while a user command waits on a strict send.
- Unload while a prefetch, RADIO fetch or source release is running.
- Peer queue replacement during a RADIO fetch or a natural-completion wait.
- Player switch or disabled switching during `on_source_selected`.
- A relayed stale position or a window trim arriving while a track plays.
- A go-away during a session, and a provider reload inside the window.

## Development and verification

```bash
scripts/setup.sh
uv run pytest
uv run ruff check provider tests
uv run ruff format --check provider tests
uv run mypy
pre-commit run --all-files
```

The test dependency follows a pinned Music Assistant `dev` commit in
`uv.lock`, together with the matching models and test-only server requirements.
Use `uv sync --extra test --frozen` before validation. Update the lock
intentionally when adopting a newer shared API; do not mix provider code with
an older globally installed Music Assistant checkout.

Most automated coverage is unit/mock based. Live Ynison, Yandex CDN, ffmpeg,
and real player transports remain integration boundaries requiring manual or
environment-backed validation.

## Known technical debt

### AudioSource lifecycle contract mismatch

Music Assistant's AudioSource lifecycle paths currently translate only
`RuntimeError` into a clean stream abort (`HTTPNotFound` on the HTTP route,
`AudioError` on the direct-PCM route). When player switching is disabled,
`on_source_selected` must abort a wrong-player selection, so it raises
`RuntimeError` as a temporary workaround instead of the more precise
`ActionUnavailable` from `music_assistant_models.errors`.

Resolution path: once upstream updates the streams controller to also accept
`ActionUnavailable` (see
[music-assistant/server#5589](https://github.com/music-assistant/server/pull/5589#discussion_r3794988694)),
replace the `RuntimeError` raise in `on_source_selected` with
`ActionUnavailable` and remove the inline NOTE plus this section.
