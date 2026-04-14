# CLAUDE.md — Yandex Ynison Plugin

## Project overview

Music Assistant plugin that makes MA players appear as devices in the Yandex
Music app via the Ynison protocol (Yandex's equivalent of Spotify Connect).

- **Type**: `PluginProvider` with `ProviderFeature.AUDIO_SOURCE`
- **Manifest type**: `plugin` (`multi_instance: true`, `depends_on: yandex_music`)
- **Domain**: `yandex_ynison`
- **Stage**: `beta` (v1.4.0)
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
  ├─ optional: pre-buffer next track + crossfade
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
  `input_format.codec_type` in-place. Every reference (PluginSource, PreBuffer,
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
| `provider/streaming.py` | PCM normalization profiles, ffmpeg pacing args, RMS diagnostics |
| `provider/prebuffer.py` | `PreBuffer` — async queue-based pre-buffering with garbage detection |
| `provider/crossfade.py` | `TailBuffer`, crossfade via MA's `StandardCrossFade` |
| `provider/protocols.py` | `YandexMusicProviderLike` — structural Protocol for yandex_music |
| `provider/yandex_auth.py` | QR auth + token refresh via `ya-passport-auth` library |
| `provider/config_helpers.py` | Sibling instance token discovery |
| `provider/constants.py` | URLs, config keys, defaults, timeouts |
| `provider/manifest.json` | Plugin metadata |

## Configuration keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `token` | SecureString | — | Yandex Music OAuth token (via QR or manual) |
| `x_token` | SecureString | — | Long-lived session token for auto-refresh (hidden) |
| `mass_player_id` | String | `__auto__` | Target MA player ID or auto-select |
| `allow_player_switch` | Boolean | `true` | Allow selecting plugin source on any player |
| `prebuffer_next_track` | Boolean | `false` | Pre-buffer next track at ~80% for gapless |
| `crossfade_duration` | Integer(0-10) | `0` | Crossfade seconds (requires prebuffer) |
| `ffmpeg_pacing` | String | `readrate` | Pacing: `readrate` / `realtime` / `unlimited` |
| `output_sample_rate` | String | `auto` | PCM sample rate: `auto` / `44100` / `48000` / `96000` |
| `output_bit_depth` | String | `auto` | PCM bit depth: `auto` / `16` / `24` |
| `publish_name` | String | `Music Assistant` | Device name in Yandex Music app |
| `device_id` | String | auto-generated | 16-char hex, persisted per instance (hidden) |

Auto-detection: `superb`/`lossless` → 24-bit/48kHz, else → 16-bit/44.1kHz.

## Track processing flow

1. **Ynison state update** → `_handle_ynison_state()` determines if our device
   is active and not paused
2. **Track change detected** → `_activate_playback()` compares `current_track_id`
   with `_current_streaming_track_id`, signals `_track_changed_event`
3. **Pre-buffer start** → `_start_prebuffer()` kicks off `run_fill()` which:
   - Fetches `StreamDetails` via `_get_stream_details_with_retry()` (cached 5min, 3 retries with exponential backoff)
   - Pipes audio through per-track ffmpeg to fixed PCM format
   - Feeds chunks into `asyncio.Queue(maxsize=64)`
   - First chunk RMS check (>55% = garbage → retry with fresh stream details)
4. **get_audio_stream()** outer loop:
   - Checks for pre-buffer hit → `_yield_from_prebuffer()`
   - Falls back to direct `_stream_track()` on miss
   - Progress synced every 5s to both MA metadata and Ynison
   - PCM frame boundary padding on interruptions
5. **Track end** → `_signal_track_completion()`:
   - Sends `progress=duration` to Ynison
   - For RADIO: replenishes queue via `get_rotor_station_tracks()`
   - Advances `current_playable_index` via `update_player_state`
   - Waits for Ynison to confirm new track (ignoring echoes)
6. **Next-track pre-buffer** → `_maybe_prebuffer_next()` triggers at 80% progress
   into a separate `_next_prebuffer` slot, promoted on actual track transition

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
- Reconnect: exponential backoff (2, 4, 8, 16, 30, 60s) with ±20% jitter, max 5 attempts
- State merging: one-level-deep dict union (sub-objects like `player_queue` and `status` are complete replacements)
- Radio queue replenishment is done by the active device via REST API — Ynison only syncs state
- Reference implementations: `bulatorr/go-yaynison` (Go), `FozerG/YandexMusicRPC` (Python)
