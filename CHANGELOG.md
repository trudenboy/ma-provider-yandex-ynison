# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Adaptive PCM format hint**: `_update_normalized_format()` now accepts an optional `hint: AudioFormat`, and a new `_prefetch_format_for_track()` runs inline in `_activate_playback` *before* `select_source()` so `PluginSource.audio_format` matches the actual incoming track. Hi-Res (96 kHz / 24-bit) lossless propagates through `auto` mode without resampling. Bounded by `_PREFETCH_FORMAT_TIMEOUT = 2.5s` so a transient API issue cannot stall activation for the full retry budget.
- **Experimental `playback_mode: handoff`**: opt-in advanced config key. In `handoff` the plugin does *not* advertise `AUDIO_SOURCE`; on Ynison track changes it calls `mass.player_queues.play_media(player_id, "<yandex_music_instance>://track/<id>", REPLACE)`, letting MA stream natively through the linked `yandex_music` MusicProvider — no inner ffmpeg, no PCM resampling. See `CLAUDE.md` → *Playback modes* for the full list of safety nets. `_features_for_mode` in `provider/__init__.py` lets `setup()` pick `SUPPORTED_FEATURES` dynamically based on the chosen mode.
- **Handoff progress heartbeat**: new advanced config key `handoff_heartbeat_interval` (3 / 5 / 7 / 10 s, default 5). Independent asyncio task pushes `update_playing_status` to Ynison even when MA's `EventType.QUEUE_TIME_UPDATED` is sparse (DLNA / UPnP renderers), guarding against `YNISON_ERROR_REBALANCED` moving the active device to the phone.
- **Handoff URI uses linked `instance_id`**: `_build_handoff_uri()` prefixes the URI with the linked yandex_music provider's `instance_id` when known (matters when borrow + own instances coexist — `mass.get_provider` would otherwise pick the first match by domain). Required adding `instance_id` to the `YandexMusicProviderLike` Protocol.
- **Handoff grace period after `play_media(REPLACE)`**: `_handoff_grace_until` (3 s, shared `_ECHO_GRACE_PERIOD` constant) suppresses spurious drift seeks while MA resolves the stream. Override: a queue already PLAYING with `corrected_elapsed_time > 1s` lets a real user seek pass through.
- **Handoff state-change force-update**: tracking `_handoff_last_seen_state`, transitions PLAYING ↔ PAUSED ↔ IDLE in MA queue bypass the 2 s progress throttle in `_on_ma_player_event`. Pause from MA UI now reflects in the Yandex Music app within ~100 ms instead of up to 2 s.
- **Handoff dedup and idle-resume**: before issuing `play_media`, the plugin compares `queue.current_item.uri` with the expected URI. Skip when already PLAYING; switch to `play()` when same URI but PAUSED. Avoids needless restart on Ynison reconnect or echo loops.
- **Handoff replay reset**: `progress_ms < 1s` on the same track clears `_handoff_completion_signaled_for` so the next end-of-track will re-signal Ynison correctly.
- **Tests**: `tests/test_provider_handoff.py` (new file, 26 tests covering `_features_for_mode`, `_handoff_activate` with all branches, `_handoff_pause`, heartbeat loop, force-progress on state change, dedup, grace, replay reset, instance-id URI, play_media-failure recovery). New cases in `tests/test_provider.py` for the format hint, pre-fetch behaviour, pre-fetch timeout, and resume-reselect pre-fetch path.

### Changed
- **Default lossless PCM rate 48 kHz to 44.1 kHz** in `PCM_LOSSLESS_PARAMS`. Yandex's primary lossless catalogue is 44.1 kHz FLAC; it no longer gets resampled. Triggered by user feedback on dastereo.ru thread post #530 ("everything was converted to 48 kHz... unlike the regular Yandex.Music provider").
- **Progress / UI sync intervals 5 s to 2 s**: `_PROGRESS_SYNC_INTERVAL` and the player-update throttle in `_handle_ynison_state` both lowered to 2 s for snappier app/MA sync. Significant changes still `force_update` immediately.
- **Echo-detection grace 5 s to 3 s**: introduced `_ECHO_GRACE_PERIOD = 3.0` constant (was hard-coded `5.0` in four call sites covering track-change, same-track resume, drift-seek, manual seek, and handoff `play_media(REPLACE)`). 3 s comfortably covers the WS round-trip plus MA stream startup; longer windows delayed legitimate user seeks issued shortly after a track change.
- **Pre-fetch fires on resume-reselect onto a *different* track**, not only when `target_player_id` itself changes (Copilot review C1). A `needs_reselect=True` driven by `_stream_stop_event` for a new track id now correctly primes `PluginSource.audio_format`.
- **`_handoff_activate` only commits `_handoff_current_track_id` after a successful `play_media`**: a failed REPLACE no longer leaves the state machine stuck in the same-track branch on the next Ynison update (Copilot review C3). Grace window also opens only on success.
- **`_handoff_activate` "track changed X to Y" log uses the captured previous id**, not the freshly-mutated attribute (Copilot review C4).

### Documentation
- `CLAUDE.md`: new "Playback modes" subsection with `stream` vs `handoff` comparison and "Handoff invariants and safety nets" listing each defensive mechanism (heartbeat, grace, dedup, replay reset, state-change force-update). Config table now includes `playback_mode` and `handoff_heartbeat_interval`. Dedup wording aligned with the actual implementation — `PlaybackState` enum has only `IDLE` / `PAUSED` / `PLAYING` / `UNKNOWN`, no separate `BUFFERING` (Copilot review C6).
- `CONF_PLAYBACK_MODE` description in `provider/__init__.py` carries explicit warnings: yandex_music dependency, queue ownership during handoff, and that `output_*` config keys do not apply in handoff mode.

### Notes
- Pre-existing mypy errors in `provider/provider.py` (`subclass Any` and `_bytes_to_ms` `Any` return) are unchanged from the `dev` baseline and not addressed in this iteration.
- Variant of handoff with a passive `PluginSource` that retains `on_play/on_pause/on_seek` callbacks was evaluated and rejected: `_get_active_plugin_source` filters by `ProviderFeature.AUDIO_SOURCE`, so without it callbacks are never invoked. Bulk `play_media([uri1, uri2, ...])` for gapless handoff is deferred to a follow-up PR (needs reverse-sync of MA queue index to Ynison `current_playable_index` via `EventType.MEDIA_ITEM_PLAYED`).

## [1.8.2] - 2026-04-28

### Fixed
- **Stale `CONF_YM_INSTANCE` selection survives YM-instance removal**: when the linked `yandex_music` instance referenced by `CONF_YM_INSTANCE` was deleted, `get_config_entries` only clamped the rendered `default_value` to `YM_INSTANCE_OWN` while leaving `selected`/`values[CONF_YM_INSTANCE]` as the stale id — so the stored config remained invalid until the user pressed Save, and a startup before that would fail with `LoginFailed("Linked Yandex Music instance '...' is not loaded")`. Now the stale id is normalized to `YM_INSTANCE_OWN` up front (and written back into `values`), so a no-touch Save persists the correction and the rest of the function reads consistent state. Dead "Selected Yandex Music instance is not available" label branch removed (PR #3614 review).

## [1.8.1] - 2026-04-23

### Fixed
- **`_yandex_provider` None-race in streaming paths**: `_get_stream_details_with_retry` and `_stream_track` used to dereference `self._yandex_provider` across `await` points. When the linked `yandex_music` MusicProvider unloaded mid-stream, the background `_check_yandex_provider_match` task would null the attribute in-between, causing `AttributeError` (and in one spot an `AssertionError`) that hard-stopped the audio generator. Both methods now capture a local reference at entry and surface a clean `LoginFailed` / stop-event exit when the provider is gone. Added two regression tests (PR #3614 review)

## [1.8.0] - 2026-04-23

### Added
- **Per-instance QR auth** (own mode): a new `Login with QR code` action button populates `CONF_TOKEN` and `CONF_X_TOKEN` from a Yandex Passport QR scan, so each plugin instance can be bound to its own Yandex account without sharing credentials with a `yandex_music` MusicProvider and without manual token paste. Multiple instances can target different accounts on different MA players.
- **Reactive 401 refresh in own mode**: when a session token (`x_token`) is stored, `_refresh_ynison_token` and `_resolve_token` refresh the music token in-memory on auth failure, mirroring borrow-mode behavior. No config writes — the refresh stays in-process for the connection lifetime.
- **`Remember session` toggle**: opt-in (default on) for storing the long-lived `x_token` after QR; off → only the short-lived music token is persisted, and expiry requires re-QR.
- **`Reset authentication` action**: clears `CONF_TOKEN`, `CONF_X_TOKEN`, and `CONF_ACCOUNT_LOGIN` in one click.
- **Account login status**: the config screen shows `Authenticated to Yandex Music as <login>` when the QR flow returns a `display_login`.

### Changed
- "Use own token" dropdown option renamed to "Use own credentials (QR or token)" to reflect the dual entry path.
- Own-mode `CONF_TOKEN` is now optional when `CONF_X_TOKEN` is stored — the plugin can mint a fresh music token on demand.

## [1.7.4] - 2026-04-22

### Fixed
- **`_wait_for_track_change` early-advance race**: the method used to `clear()` `_track_changed_event` before inspecting state, so a state update that arrived between `_signal_track_completion()` returning and the wait starting lost its `set()` signal — the stream stalled for the full 30s timeout and then gave up. Now the state is checked before the clear, and the method returns immediately when Ynison has already advanced. Added a regression test; also fixed pre-existing out-of-bounds `current_playable_index` values in two existing tests that were masking the issue (PR #3614 review)

## [1.7.3] - 2026-04-22

### Changed
- **Task creation**: replaced all 4 `asyncio.ensure_future(...)` sites in `ynison_client.py` (reconnect + message loop) with `asyncio.create_task(...)` — drop-in for plain coroutines, binds to the running loop without the legacy loop-selection path (PR #3614 review)

## [1.7.2] - 2026-04-22

### Changed
- **Reconnect backoff**: `RECONNECT_DELAYS` is now `(5s, 10s, 30s, 60s, saturating)` to match the schedule advertised in 1.7.0 notes — previously the constant still held the legacy `(2, 4, 8, 16, 30, 60)s` tuple inherited from the capped-retry design (PR #3614 review)

### Removed
- Dead `CONF_FFMPEG_PACING` / `PACING_REALTIME` constants and the `FFmpeg pacing mode` docs row — never wired into a `ConfigEntry`; `pacing_args()` always returns `['-re']`. Drop the misleading config surface rather than pretending it's tunable (PR #3614 review)

## [1.7.1] - 2026-04-21

### Fixed
- **Output format overrides**: `_update_normalized_format` now rejects stale/tampered `output_sample_rate`/`output_bit_depth` config values (off-list strings, unparsable input) and falls back to the auto-detected base with a warning instead of raising `ValueError` or silently producing an inconsistent `content_type`/`bit_depth` pair (PR #3614 review)

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
