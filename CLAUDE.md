# CLAUDE.md — Yandex Ynison Plugin

## Project overview

Music Assistant plugin that makes MA players appear as devices in the Yandex
Music app via the Ynison protocol (Yandex's equivalent of Spotify Connect).

- **Type**: `PluginProvider` with `ProviderFeature.AUDIO_SOURCE`
- **Manifest type**: `plugin` (`multi_instance: true`, `depends_on: yandex_music`)
- **Domain**: `yandex_ynison`
- **Stage**: `beta` (v2.0.0)
- **Architecture reference**: `spotify_connect` provider in MA server

## Architecture

```
Yandex Music app (phone/web/desktop)
  │
  ▼
Ynison WebSocket  ◄──►  YnisonClient (ynison_client.py)
  │                         │  two-step: Redirector → State Service
  │                         │  JSON over WebSocket (gRPC-like framing)
  ▼
YandexYnisonProvider (provider.py)
  │
  ├─ receives track_id from Ynison PlayerState
  ├─ resolves StreamDetails via linked yandex_music provider
  ├─ fetches audio from Yandex CDN (raw or encrypted FLAC/MP3/AAC)
  ├─ per-track ffmpeg → fixed PCM (s16le or s24le)
  │
  ▼
PluginSource → MA Player (Chromecast / DLNA / AirPlay / etc.)
  │
  └─ on play/pause/seek/next/prev → update_playing_status → Ynison
```

### Key architectural invariants

- **Passive player**: MA never manipulates `current_playable_index` on
  auto-advance. Yandex controls the queue; MA signals completion and waits.
  Exception: RADIO queues where the active device replenishes via REST API.
- **Session-frozen format**: `get_audio_stream()` freezes `_normalized_params`
  at session start. Mid-session format changes (e.g. provider reload) only
  apply on the next session.
- **Fresh AudioFormat copies**: `AudioFormat` is mutable; MA's ffmpeg mutates
  `input_format.codec_type` in-place. Every reference (PluginSource,
  ffmpeg output_format) uses a fresh `make_pcm_format()` copy.
- **Progress clamped**: Ynison rejects `progress > duration` (error 400030001,
  disconnects WS). Always `min(progress_ms, duration_ms)` before sending.
- **Echo detection**: After sending `update_playing_status`, Ynison echoes it
  back. The plugin tracks last-sent values (±2s / 5s window) to prevent
  false seek detection.

## Key modules

| File | Purpose |
|------|---------|
| `provider/__init__.py` | Setup function, config entries, `SUPPORTED_FEATURES` |
| `provider/provider.py` | `YandexYnisonProvider(PluginProvider)` — main plugin class |
| `provider/ynison_client.py` | `YnisonClient` — WebSocket client for Ynison protocol |
| `provider/streaming.py` | PCM normalization profiles, ffmpeg pacing args |
| `provider/protocols.py` | `YandexMusicProviderLike` — structural Protocol for yandex_music |
| `provider/yandex_auth.py` | QR auth + token refresh via `ya-passport-auth` library |
| `provider/config_helpers.py` | Sibling instance token discovery |
| `provider/constants.py` | URLs, config keys, defaults, timeouts |
| `provider/manifest.json` | Plugin metadata |

## Configuration keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ym_instance` | String (dropdown) | auto | Source of OAuth credentials: a `yandex_music` instance id (borrow), or `__own__` (per-instance own credentials via QR or manual paste) |
| `token` | SecureString | — | Yandex Music OAuth token (own mode; populated by QR or manual entry) |
| `x_token` | SecureString | — | Long-lived session token for own-mode reactive 401 refresh (hidden) |
| `account_login` | String | — | Display login from QR (own mode); shown in the status label (hidden) |
| `remember_session` | Boolean | `true` | Own mode: store `x_token` after QR for auto-refresh |
| `mass_player_id` | String | `__auto__` | Target MA player ID or auto-select |
| `allow_player_switch` | Boolean | `true` | Allow selecting plugin source on any player |
| `output_sample_rate` | String | `auto` | PCM sample rate: `auto` / `44100` / `48000` / `96000`. Auto adapts to first track via `_prefetch_format_for_track` (lossless 44.1 / 96 kHz preserved). |
| `output_bit_depth` | String | `auto` | PCM bit depth: `auto` / `16` / `24`. Auto adapts to first track. |
| `playback_mode` | String | `stream` | `stream` (default, plugin owns audio source) or `handoff` (experimental, MA player_queue plays via yandex_music). Affects `SUPPORTED_FEATURES` at setup. |
| `handoff_heartbeat_interval` | String (`3`/`5`/`7`/`10`) | `5` | Handoff-only: how often to push `update_playing_status` to Ynison even without MA queue events. Guards against `YNISON_ERROR_REBALANCED`. Ignored in stream mode. |
| `publish_name` | String | `Music Assistant` | Device name in Yandex Music app |
| `device_id` | String | auto-generated | 16-char hex, persisted per instance (hidden) |

Three reachable auth states:
- **Borrow** — `ym_instance` points at a `yandex_music` instance; tokens read live from there.
- **Own + x_token** — `ym_instance == __own__`, `x_token` set; reactive 401 refresh works.
- **Own + token only** — `ym_instance == __own__`, `x_token` empty (manual paste, or QR with Remember session off); expiry needs re-paste/re-QR.

Auto-detection (no hint): `superb`/`lossless` → 24-bit/44.1kHz, else → 16-bit/44.1kHz. With hint from real `stream_details.audio_format` (pre-fetched on `_activate_playback` before `select_source`), auto mode lifts to actual rate (e.g. 96 kHz for Hi-Res). Explicit `output_sample_rate` / `output_bit_depth` always win over the hint.

### Playback modes

- **stream** (default): plugin advertises `AUDIO_SOURCE`, owns a `PluginSource` and emits PCM via `get_audio_stream()` → MA's outer ffmpeg → player. Two ffmpeg passes (inner per-track + outer per-session).
- **handoff** (experimental): plugin does NOT advertise `AUDIO_SOURCE`. On Ynison track change it calls `mass.player_queues.play_media(player_id, "<yandex_music_instance>://track/<id>", REPLACE)`. MA streams natively through the linked `yandex_music` MusicProvider → no inner ffmpeg, no PCM resampling. Pause/seek/track-end mirror back to Ynison via subscription on `EventType.QUEUE_TIME_UPDATED` / `PLAYER_UPDATED`. Trade-off: looser sync between the Yandex Music app and MA — Spotify Connect avoids this for the same reason (see commented `CONF_HANDOFF_MODE` in `spotify_connect/__init__.py`).

#### Handoff invariants and safety nets

- **URI uses linked instance_id**, not bare `yandex_music://` — picks the correct yandex_music account when both borrow and own coexist (`_build_handoff_uri`).
- **Heartbeat** (`_handoff_heartbeat_loop`): runs at `handoff_heartbeat_interval` (default 5s, configurable 3–10s). Pushes progress to Ynison even when MA's `QUEUE_TIME_UPDATED` is sparse (DLNA/UPnP), preventing Ynison from re-balancing the active device.
- **Grace periods** (since v2.0): split into two distinct windows. `_drift_suppress_until` (`_DRIFT_SUPPRESS_PERIOD = 5s`) suppresses drift-driven seeks while MA spins up the stream after `play_media(REPLACE)` or a `seek`; `_re_issue_debounce_until` (`_REISSUE_DEBOUNCE_PERIOD = 3s`) blocks another REPLACE while the previous one is still resolving (prevents the IDLE-resume re-issue loop where each `paused=False` echo would re-fire). Override: a queue already PLAYING with `elapsed > 1s` lets a real user seek pass through. Stream mode still uses the older `_seek_grace_until` / `_ECHO_GRACE_PERIOD = 3s` for track change / seek / same-track resume.
- **Dedup on reconnect**: before issuing `play_media`, compare `queue.current_item.uri` with the expected URI. Skip when already PLAYING; switch to `play()` when same URI but PAUSED. (`PlaybackState` enum exposes only `IDLE` / `PAUSED` / `PLAYING` / `UNKNOWN` — there is no separate `BUFFERING` state.)
- **Replay reset** (`progress_ms < 1000`): clears `_handoff_completion_signaled_for` so the next end-of-track will re-signal Ynison.
- **State-change force-update** (P10): MA queue transitions (PLAYING ↔ PAUSED ↔ IDLE) bypass the 2s progress throttle — pause/play from MA UI reflect in the Yandex Music app within ~100 ms.
- **Owner conflict**: handoff mode treats the MA queue as owned by Ynison. Starting playback from the Yandex Music app calls `play_media(REPLACE)`, which silently overwrites any queue the user built in MA UI.
- **Audio quality** in handoff is governed by the `yandex_music` provider's `quality` setting, not by this plugin's `output_sample_rate` / `output_bit_depth` (those apply only to stream mode).

#### Handoff FSM (since v2.0)

Two-way sync uses an explicit phase model. The plugin tracks `_expected_phase: HandoffPhase` (values `IDLE`, `ACTIVATING`, `PLAYING`, `PAUSED`, `ENDING`) alongside `_expected_track_id`. `(MA queue.state, _expected_phase)` is the disambiguation pair:

| MA queue.state | _expected_phase | Action |
|----------------|-----------------|--------|
| `PLAYING` | `ACTIVATING` | Transition expected → `PLAYING` (set in `_on_ma_player_event` on first PLAYING tick). |
| `PLAYING` | `PLAYING` | Steady state; only drift-seek logic runs. |
| `PAUSED` | `PLAYING` | User paused via MA UI; `_on_ma_player_event` mirrors `paused=True` to Ynison. |
| `IDLE` | `ENDING` | Natural end-of-track (`elapsed >= duration - 5s`); `_signal_track_completion` to Ynison. |
| `IDLE` | `PAUSED` | 30s pause watchdog; resume re-issues `play_media + seek` with `_handoff_last_playing_elapsed_ms`. |
| `IDLE` | `ACTIVATING` | Stream still resolving; `_drift_suppress_until` blocks seeks. |

**Echo classification** uses Lamport-style version watermarks (`_pending_outbound_queue_version`, `_pending_outbound_status_version`) plus author check on **both** version blocks. An incoming state is our echo only when both are authored by us *and* their inbound versions are `<=` our pending watermarks. Replaces the previous OR-then-AND device-id-only heuristics that misclassified peer state changes.

**Reconnect settle window** (`_post_reconnect_settle_until`, 2s): the first Ynison broadcast after reconnect is dropped to avoid acting on pre-reconnect peer state. `_connect_state` sends a fresh initial state, never the cached `self.state.player_state`.

**Idempotency** (`_idempotent`, TTL `_COMMAND_IDEMPOTENCY_TTL = 1s`): duplicate `(action, key)` pairs (e.g. two pauses for the same player_id within 1s) collapse to a single command. Prevents Ynison-echo storms from issuing the same MA call multiple times.

**Cancel-on-track-change** (`_cancel_pending_play_media`): a still-running `play_media` task is cancelled before issuing a new one. Rapid `next` taps used to fire several back-to-back; cancellation avoids a half-finished load racing the new one.

## Track processing flow

1. **Ynison state update** → `_handle_ynison_state()` determines if our device
   is active and not paused
2. **Track change detected** → `_activate_playback()` compares `current_track_id`
   with `_current_streaming_track_id`, signals `_track_changed_event`
3. **get_audio_stream()** outer loop:
   - Streams via `_stream_track()` which fetches StreamDetails
     (cached 5min, 3 retries with exponential backoff), pipes audio through
     per-track ffmpeg to fixed PCM format
   - Progress synced every 5s to both MA metadata and Ynison
   - PCM frame boundary padding on interruptions
4. **Track end** → `_signal_track_completion()`:
   - Sends `progress=duration` to Ynison
   - For RADIO: replenishes queue via `get_rotor_station_tracks()`
   - Advances `current_playable_index` via `update_player_state`
   - Waits for Ynison to confirm new track (ignoring echoes)

## Development setup

```bash
cd /Users/renso/Projects/ma-provider-yandex-ynison
scripts/setup.sh       # or: uv sync --extra test
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy            # type check
```

## CI infrastructure

Uses reusable workflows from `trudenboy/ma-provider-tools`:
- `reusable-test.yml` — pytest, ruff, mypy, codespell
- `reusable-release.yml` — tag-based releases
- `reusable-security.yml` — dependency audit
- `reusable-sync-to-fork.yml` — fork sync for MA server integration
  - Has TWO sed rewrites for tests: import paths and string literals (mock.patch)
  - Default target branch: `integration/dev`; for upstream PR use `target_branch=upstream/yandex_ynison`

## Ynison protocol notes

- Transport: JSON over WebSocket (gRPC-like framing, not binary protobuf)
- Two-step connection: Redirector → State Service
- Redirect URL: `wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison`
- State URL: `wss://{host}/ynison_state.YnisonStateService/PutYnisonState`
- Auth: `Authorization: OAuth {token}`, device info in `Sec-WebSocket-Protocol` header
- Reconnect: exponential backoff (5, 10, 30, 60s saturating) with ±20% jitter, retries indefinitely
- State merging: top-level sub-object replacement (Ynison sends `player_queue` and `status` as complete objects, so each top-level key is replaced wholesale; top-level keys absent from an update are retained)
- Radio queue replenishment is done by the active device via REST API — Ynison only syncs state
- Reference implementations: `bulatorr/go-yaynison` (Go), `FozerG/YandexMusicRPC` (Python)
