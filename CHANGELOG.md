# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2026-04-11

### Added
- Multi-instance token sharing: new instances auto-detect and reuse token from existing ones
- Instance name postfix: multiple instances show device name in UI (e.g. `[Living Room]`)
- Ynison error response handling: errors are logged and no longer crash the connection loop
- Queue exhaustion completion signal: Ynison is notified when queue ends so controller can push more tracks (radio/My Wave)
- `_best_duration_ms` helper: prefers actual stream duration over Ynison state value
- 8 new tests for token sharing, instance naming, queue exhaustion, and duration handling

### Fixed
- Volume changes no longer break Ynison connection (volume sync removed — MA controls physical player independently)
- Duration now synced from actual audio stream, not Ynison metadata (fixes premature track stop)
- Stale `duration_ms` no longer propagated on track advance — reset to 0 when switching tracks
- Progress bar shows correct position after seek from Yandex Music app (upstream PR #3652 merged)
- Queue exhaustion no longer freezes YM app — stream stops cleanly and restarts via `select_source`

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
