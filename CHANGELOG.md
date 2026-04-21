# Changelog

All notable changes to this project will be documented in this file.

## [1.7.1] - 2026-04-21

### Fixed
- **Output format overrides**: `_update_normalized_format` now rejects stale/tampered `output_sample_rate`/`output_bit_depth` config values (off-list strings, unparseable input) and falls back to the auto-detected base with a warning instead of raising `ValueError` or silently producing an inconsistent `content_type`/`bit_depth` pair (PR #3614 review)

## [1.7.0] - 2026-04-21

### Fixed
- **Ynison state protocol hardening**: all outbound `version`/`timestamp_ms`/`progress_ms`/`duration_ms`/`player_action_timestamp_ms` fields are string-typed (integers trigger HTTP 500 + WS teardown)
- **Echo detection**: replaced the ±2s/5s heuristic timing window with `version.device_id`-based author inspection on both `player_queue` and `status` blocks — catches queue and status-only echoes alike, eliminates false positives when peer seeks happen to match our last-sent timing
- **Inbound state normalization**: `_parse_state` coerces int timestamp fields to strings at ingestion, so the reconnect path (`send_full_state(self.state.player_state)`) and queue edits (`update_player_state` shallow-copying `status`) stay safe by construction regardless of what peers inject
- **Own-authored state**: `_advance_queue_index`/`_update_queue_list` now stamp their own `version` block on outbound `player_queue`/`status` so Ynison sees the correct author and downstream echo detection works

### Changed
- **Reconnect**: retries indefinitely with exponential backoff + ±20% jitter (5s → 10s → 30s → 60s, saturating). Previously capped at 5 attempts, which surrendered the session on short network outages

### Removed
- `on_disconnect` callback on `YnisonClient` (dead API — the plugin never observed it)
- `MAX_RECONNECT_ATTEMPTS` constant
- Heuristic echo-tracking fields (`_ECHO_TOLERANCE_MS`, `_ECHO_WINDOW_S`, `_last_sent_to_ynison_ms`, `_last_sent_to_ynison_time`)

## [1.6.0] - 2026-04-20

### Added
- **Borrow tokens from yandex_music**: new default auth mode reads OAuth credentials from a linked `yandex_music` MusicProvider instance — no duplicate QR flow, no separate token storage. A `Yandex Music source` dropdown in config picks which YM instance to borrow from. Own-mode (manual token paste) remains as an escape hatch and is preserved on upgrades from standalone configs.
- Reactive token refresh from `x_token` on 401 (in-memory only; scheduled refresh stays with the `yandex_music` provider)

### Changed
- **State merging**: replaced nested merge of `player_state` sub-objects with top-level replacement — Ynison sends `player_queue` and `status` as complete objects, so merging retained stale keys absent from the update
- `YandexMusicProviderLike` Protocol: removed `get_quality()` (not implemented by the in-tree yandex_music provider); quality is now read from the shared `ProviderConfig`

### Fixed
- **Quality auto-detection**: `_update_normalized_format` reads the yandex_music quality tier from `provider.config.get_value("quality")` instead of the non-existent `get_quality()` method, so superb/lossless quality correctly maps to 24-bit/48 kHz PCM without manual overrides (PR #3614 review)

## [1.5.4] - 2026-04-16

### Fixed
- **Reconnect state restoration**: restore last-known player state on Ynison reconnect after re-balance (previously the client returned to empty state post-reconnect)

## [1.5.3] - 2026-04-15

### Changed
- Required Python version bumped to >= 3.14

### Fixed
- Raise `PlayerCommandFailed` when the Ynison WebSocket is disconnected (previously failed silently)
- Restore provider-specific deps in `pyproject.toml` after workflow-wrapper sync
- Correct assert-guard comment in `_stream_track`

## [1.5.2] - 2026-04-15

### Removed
- **Unlimited pacing mode**: removed `PACING_UNLIMITED`, `CONF_FFMPEG_PACING` config entry; realtime (`-re`) is now always applied

## [1.5.1] - 2026-04-15

### Fixed
- CI: fixed `certifi` dependency resolution failure caused by PyTorch index priority in `uv pip install` (added `--index-strategy unsafe-best-match` to `ma-provider-tools`)

## [1.5.0] - 2026-04-15

### Removed
- **Pre-buffer system**: removed `prebuffer.py`, `PreBuffer`, `run_fill`, `_start_prebuffer`, `_yield_from_prebuffer`, `_maybe_prebuffer_next` — simplifies streaming to direct `_stream_track()` path
- **Crossfade**: removed `crossfade.py`, `TailBuffer`, `_do_crossfade`, `apply_crossfade`, `collect_crossfade_head` — MA's outer ffmpeg handles transitions
- **RMS diagnostics**: removed `compute_rms_pct`, `log_first_chunk`, 24-bit PCM constants from `streaming.py`
- **Readrate pacing**: removed `readrate 1.1x + burst` FFmpeg pacing mode; default changed to `realtime (-re)`
- Config entries: `prebuffer_next_track`, `crossfade_duration`
- ~2,800 lines of code and tests removed

### Changed
- FFmpeg pacing default changed from `readrate` to `realtime (-re)`
- Pacing options reduced to: `realtime` (default) and `unlimited`

## [1.4.0] - 2026-04-13

### Added
- **Crossfade**: smooth audio transitions between tracks using MA's `StandardCrossFade` engine, configurable 0–10s (default off)
- **API throttling & retry**: `ThrottlerManager` rate-limits Yandex API calls; exponential backoff with jitter on transient failures
- **Stream details cache**: `mass.cache` integration with 5-minute TTL eliminates redundant API calls for repeated tracks
- **PreBuffer ready event**: `ready_threshold` signals when enough audio is buffered, enabling precise crossfade timing
- New modules: `provider/crossfade.py`, `provider/prebuffer.py`, `provider/protocols.py`, `provider/streaming.py`
- 157 new tests (88 → 245 total), ynison_client coverage 55% → 96%, provider coverage 59% → 70%

### Changed
- `YandexMusicProviderLike` Protocol: replaced `client`/`config` properties with typed `get_rotor_station_tracks()` and `get_quality()` methods — eliminates tight coupling to yandex_music internals
- Crossfade output wrapped with `iter_pcm_slices()` for frame-aligned ~100ms chunks
- PreBuffer `cancel()` uses `close_async_generator()` for safe generator cleanup
- Crossfade fallback uses `align_audio_to_frame_boundary()` for PCM alignment
- `_bytes_to_ms()` uses `AudioFormat.pcm_sample_size` instead of manual byte_rate calculation

### Fixed
- Atomic EOF sentinel delivery in prebuffer prevents race conditions
- 30-second timeout on `prebuffer.queue.put()` prevents silent hangs
- `assert` replaced with `RuntimeError` in ynison_client for production safety
- Device ID generation uses `secrets.token_hex` instead of predictable random
- mypy `no-any-return` resolved in `_get_target_player_id`

### Security
- Device ID generation hardened with cryptographically secure `secrets` module

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
