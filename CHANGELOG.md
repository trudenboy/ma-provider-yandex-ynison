# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-04-12

### Added
- **FLAC passthrough**: eliminated local ffmpeg transcoding — raw audio bytes (FLAC/MP3/AAC) now pass directly from Yandex CDN to MA's ffmpeg, removing one entire ffmpeg process from the pipeline
- **Pre-buffer system**: audio download starts immediately on Ynison track change (before the player HTTP GET arrives), hiding API and CDN latency from the critical playback path
- `PreBuffer` dataclass with asyncio.Queue-based producer/consumer, automatic cancellation, and error fallback

### Changed
- PluginSource `audio_format` changed from `PCM_S16LE` to `FLAC` — MA now receives native audio format instead of pre-decoded PCM
- `_stream_track` simplified: raw passthrough for normal playback, ffmpeg fallback only for seek operations
- `get_audio_stream` now checks for matching prebuffer before streaming directly

### Fixed
- Reduced playback start delay by ~3-5 seconds (from ~15-20s to ~10-12s) on all player types; further improvement requires MA server-side change (`-re` → `-readrate_initial_burst`)

## [1.2.1] - 2026-04-11

### Added
- Radio/wave queue replenishment via Yandex Music REST API (`get_rotor_station_tracks`) — RADIO queues now auto-advance indefinitely
- Prefetch optimization: background fetch of next track batch when playing second-to-last item in queue
- `depends_on: "yandex_music"` in manifest — MA auto-loads ynison when yandex_music is available and cascade-unloads when removed
- `_wait_for_track_change()` helper that ignores Ynison echoes and waits for actual track ID change
- 4 new tests for radio replenishment, prefetch, and echo-resistant track change wait

### Fixed
- Race condition on track completion: Ynison echo of `update_playing_status` triggered false seek detection, causing old track to re-stream at seek=end, then new track to start at wrong position
- Active device now increments `current_playable_index` itself (Ynison is state-sync, not command protocol)
- RADIO/wave queues no longer stall at end — tracks fetched via YM API instead of relying on `sync_state_from_eov` (which only works for non-radio entities)

### Removed
- EOV-based queue replenishment (replaced by direct REST API calls)

## [1.2.0] - 2026-04-11

### Added
- Multi-instance token sharing: new instances auto-detect and reuse token from existing ones
- Instance name postfix: multiple instances show device name in UI (e.g. `[Living Room]`)
- Ynison error response handling: errors are logged and no longer crash the connection loop
- Queue exhaustion completion signal: Ynison is notified when queue ends so controller can push more tracks (radio/My Wave)
- SyncStateFromEOV: requests EOV backend to replenish the queue when exhausted (first known implementation of this Ynison feature)
- `_best_duration_ms` helper: prefers actual stream duration over Ynison state value
- 8 new tests for token sharing, instance naming, queue exhaustion, and duration handling

### Fixed
- Volume changes no longer break Ynison connection (volume sync removed — MA controls physical player independently)
- Duration now synced from actual audio stream, not Ynison metadata (fixes premature track stop)
- Stale `duration_ms` no longer propagated on track advance — reset to 0 when switching tracks
- Progress bar shows correct position after seek from Yandex Music app (upstream PR #3652 merged)
- Queue exhaustion no longer freezes YM app — stream stops cleanly and restarts via `select_source`
- Next track unavailable after auto-advance — MA no longer manipulates queue index; Yandex controls the queue

### Changed
- Plugin stage promoted from `alpha` to `beta`

### Removed
- Volume sync to Ynison (was causing 400/500 errors and connection drops)

## [1.1.0] - 2026-04-10

### Changed
- Migrated authentication from hand-rolled QR/OAuth code to `ya-passport-auth` library
- Token handling now uses `SecretStr` throughout the pipeline for improved security
- All `ya-passport-auth` exceptions mapped to Music Assistant `LoginFailed`
- `_resolve_token` re-raises `LoginFailed` with original message from refresh errors
- Docker init script auto-detects `uv`/`pip` with fallback

### Added
- `ya-passport-auth>=1.0.0` as runtime dependency
- `tests/test_yandex_auth.py` — 9 unit tests for auth functions (QR flow, refresh, validate)

### Removed
- ~200 lines of manual Passport OAuth/QR authentication code (`YandexQRAuth` class)
- Manual CSRF extraction, cookie jar handling, QR polling logic

## [1.0.0] - 2026-04-08

### Added
- Ynison WebSocket client with two-step connection (redirector + state service)
- Plugin provider with `PluginSource` and `AUDIO_SOURCE` feature
- Audio streaming via linked Yandex Music provider with ffmpeg PCM conversion
- Continuous stream with automatic track change detection
- QR code authentication (shared with Yandex Music provider)
- Playback control: play/pause, next/previous, seek, volume
- Auto and manual MA player selection
- Player switch protection option
- Device registration with persistent device ID
- Reconnection with exponential backoff
- Cover art display from Ynison state
- Docker Compose dev environment for local testing

## [Unreleased]
