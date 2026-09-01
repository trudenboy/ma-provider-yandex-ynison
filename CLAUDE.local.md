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
- **Player-owned exclusivity.** `on_source_selected` claims
  `_in_use_by_player`; `playback_session_id` rejects teardown callbacks from
  superseded requests on the same player.
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
| `provider/provider.py` | AudioSource lifecycle, streaming, control sync, metadata, and queues |
| `provider/ynison_client.py` | Ynison transport, messages, state, reconnect, and strict sends |
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
clears legacy auth keys rather than transferring credentials. Legacy `__auto__`
setups fail with `no_connected_player` until a concrete player is selected.

### Runtime values

| Key | Default | Meaning |
|-----|---------|---------|
| `allow_player_switch` | `true` | Allow this source to move to another player |
| `stream_mode` | `stable` | `stable` or per-track `max_quality_dynamic` PCM sessions |
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

`max_quality_dynamic` is eligible only for Yandex Music `Superb` quality with
both output overrides set to `auto`. It accepts real source rates from 8 through
384 kHz, maps source precision to PCM16/24/32, and selects the highest player
rate not above the source when possible. The effective signature is frozen per
session and recalculated for the actual player/bridge/group in
`on_source_selected`.

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

Dynamic mode prefetches the current and immediate next playable ID in the
background. Equal effective signatures continue the current generator. A
changed signature ends it on a PCM-frame boundary without signalling natural
completion, rebuilds the AudioSource format, and reissues `play_media` for the
same queue from the latest Ynison progress. A mixed-format boundary may be
audible and can skip elapsed time because the Ynison clock keeps running.

## Ynison transport and recovery

The transport performs:

1. redirector WebSocket authentication;
2. ticket/session extraction;
3. state-service WebSocket authentication;
4. fresh device/full-state registration;
5. passive-event muting request;
6. message-loop state dispatch.

Transient failures reconnect indefinitely using 5, 10, 30, and 60 second
saturated delays with ±20% jitter. Only one reconnect task may exist. Strict
sends raise `YnisonSendError` for user commands and delivery-critical queue
updates; periodic progress and prefetch publications remain best-effort.
An empty redirect ticket shares a one-attempt credential-refresh budget with
401/403 failures for each reconnect episode.

## Radio queues

When a `RADIO` queue reaches its final two items, the provider prefetches
rotor tracks through the linked Yandex Music provider. It maps returned tracks
to Ynison queue items and publishes the expanded list. At natural track end it
uses prefetched data when available, otherwise fetches synchronously, advances
the queue version/index, and waits for a different track id or queue position.
Shuffle mappings are extended with the new original indices. Repeat ONE restarts
the current item; repeat ALL wraps finite queues; repeat NONE stops at their end.

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
