# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2026-05-08

### Live-test driven stabilisation + FSM dispatch refactor

Continuation of v2.0 architectural work, addressing the issues surfaced in live testing of v2.0:
1. Repeated `play_media(REPLACE)` on rapid pause/play tap landing in IDLE-resume race.
2. ~3-5s "button unresponsive" delay after pause in the Yandex app.
3. Restart-from-zero glitch on resume (play_media(REPLACE) decodes from 0 before our seek lands).
4. Drift-detect treating queue-rebuild `progress=0` echoes as user seeks, yanking playback to start mid-track.

### Added — handoff dispatcher refactor (`provider/provider.py`)

`_handoff_activate` is now a thin centralized FSM dispatcher (~30 lines) that classifies each Ynison state event and routes it to one of three explicit action methods:

- `_apply_track_change` — handles new-track scenarios (PLAYING dedup, PAUSED → cmd_play resume, else REPLACE with cancel-on-track-change).
- `_apply_idle_resume` — re-issues play_media when MA's queue has dropped to IDLE on the same URI (post pause-watchdog), with cmd_pause/seek/cmd_play sequence to avoid the audible 0-then-jump glitch.
- `_apply_same_track_sync` — drift-seek detection (with queue-rebuild guard) and queue-PAUSED → cmd_play resume mirror.

Each method's contract is documented; the dispatcher itself only branches on (track changed?, queue.state, queue.current_item.uri). This eliminates the previous 200-line `_handoff_activate` blob and makes the decision flow auditable.

### Changed — pause via `mass.players.cmd_pause` / resume via `cmd_play`

Switched from `mass.player_queues.pause` / `play` to `mass.players.cmd_pause` / `cmd_play` for handoff pause and resume operations. The queue-level pause schedules MA's `_watch_pause` watchdog that drops queue.state to IDLE within seconds for a single-track REPLACE queue, forcing every resume through play_media(REPLACE) → 3-5s of silence. cmd_pause directly on the player keeps queue.state == PAUSED for as long as the user wants and lets resume go through the fast path.

### Changed — paused resolver priority

Heartbeat / `_on_ma_player_event` now resolve `is_paused` via:
1. `_expected_phase == PAUSED` → True (user pause is authoritative; was previously losing to activation window for up to 10s, leaving the Yandex-app button "unresponsive");
2. `_drift_suppress_until > now` → False (we're activating; queue's brief IDLE shouldn't bleed through);
3. `queue.state != PLAYING` → True.

### Added — immediate paused echo + activation timing fixes

- `_handoff_pause` now closes `_drift_suppress_until` immediately and pushes one paused=True update to Ynison without waiting for the next heartbeat tick. Yandex-app button reflects state in <500ms instead of 3-5s.
- `_drift_suppress_until` / `_re_issue_debounce_until` / `_expected_phase` are set BEFORE awaiting `play_media` (in both `_apply_track_change` and `_apply_idle_resume`). MA fires PLAYER_UPDATED events while play_media is still resolving; without the windows pre-set, those events leaked stale `paused=True` to Ynison and triggered duplicate-REPLACE races.
- Same for `_handoff_pause`: `_expected_phase = PAUSED` is set BEFORE awaiting cmd_pause (rolled back on exception).

### Added — drift-seek-to-0 guard

Drift-seek now skips when Ynison reports progress<1s while MA is already past 5s. RADIO queue rebalances broadcast a fresh state with progress=0 for the same track; obeying it as a real user seek yanked playback back to the start mid-track. Genuine user seek to 0 is rare and resolves on the next state update.

### Added — IDLE-resume cmd_pause/seek/cmd_play dance

`_apply_idle_resume` now wraps the seek with `cmd_pause` before and `cmd_play` after. play_media(REPLACE) starts decoding at position 0; naive seek alone leaks ~1-2s of "from 0" audio before landing. Pause-seek-play sequence trades that for brief silence.

### Changed — `_REISSUE_DEBOUNCE_PERIOD` 3s → 8s, `_DRIFT_SUPPRESS_PERIOD` 5s → 10s

Three seconds turned out to be too short — heartbeat at T+3.5s reported `paused=True` (queue still IDLE while stream loading), the Yandex app showed pause, the user re-tapped play, a second REPLACE fired and raced the first. Eight seconds comfortably covers real Chromecast/DLNA/web-player startup latency. Drift suppress bumped in tandem to keep the activation window aligned end-to-end.

### Refactored — Ynison echo classification (`provider/ynison_client.py`)

Cleaned up the v2.0 Lamport-style version-watermark code. Research of go-yaynison's proto schemas confirmed `version.version` is documented as `random(int64)` and the server re-stamps it after every `update_playing_status`; comparing inbound watermarks against outbound was a no-op (the existing check always fell through to author=ours). Echo detection now uses author check on both queue.version.device_id AND status.version.device_id explicitly, with documentation of why authorship is the only reliable signal.

### Added — `update_session_params(mute_events_if_passive=True)`

New `YnisonClient.update_session_params` method, called automatically right after `send_full_state` on every connection. Tells Ynison's server not to forward peer state updates while we're not the active device, reducing inbound noise (and CPU) in borrow mode alongside other subscribers and removing a class of false positives in echo classification (fewer messages → fewer chances to misclassify).

### Added — shared helpers between stream and handoff modes

Two static helpers extracted to centralise duplicated logic and bring stream-mode parity for fixes previously only in handoff:

- `_classify_drift(ynison_ms, our_ms, threshold_ms=3000)` returns one of `"ignore"` / `"queue_rebuild"` / `"seek"`. The queue-rebuild guard (Ynison reports near-zero while local position is past 5s → not a real seek) is now applied to stream mode too — RADIO replenishment used to yank the stream player back to the start mid-track on every queue rebalance, just like handoff before v2.1. Used in both `_activate_playback` (stream) and `_apply_same_track_sync` (handoff).
- `_pick_resume_position(local_snapshot_ms, ynison_progress_ms)` returns `(resume_ms, source)`. Takes max of local snapshot and Ynison-reported progress so a stale local accumulator (handoff: reset by every play_media REPLACE; stream: reset by network blip) never beats the user-authoritative Ynison position. Used in `_apply_idle_resume`.

Idempotency cache extended to stream-mode `_on_play` / `_on_pause` callbacks: a duplicate MA pause/play event within 1s collapses to a single `update_playing_status` Ynison call.

### Live-test validated

Pause / resume / next / prev / seek / mid-track-handoff / natural-end auto-advance confirmed working correctly in both `playback_mode: stream` and `playback_mode: handoff` after v2.1 refactor + shared helpers.

### Added — Mid-track handoff activation seek

When the user transfers playback from the Yandex app to MA mid-track (track at e.g. 60s in app → tap MA device), `_apply_track_change` now honors `state.progress_ms` and seeks to it via the same `cmd_pause`/`seek`/`cmd_play` dance used by `_apply_idle_resume`. Previously MA always restarted from 0.

### Added — Natural-end completion via state-transition + heartbeat fallback

Auto-advance after natural end-of-track is now driven by two complementary detectors:
- **Event-driven** (`_on_ma_player_event`): observes the `PLAYING → IDLE` queue state transition, gated on `_expected_phase == HandoffPhase.PLAYING` and `_is_at_natural_end_of_track(queue)`. Disambiguates from user pause via the phase guard (`_handoff_pause` flips `_expected_phase = PAUSED` before awaiting `cmd_pause`).
- **Heartbeat-driven** (`_handoff_heartbeat_loop`, every ≤5s): polls the same condition. MA's event bus occasionally drops the PLAYING → IDLE transition for handoff (live trace observed); the heartbeat poll catches it on the next tick.

`MEDIA_ITEM_PLAYED` was tried first but turned out to fire prematurely on seek-on-activation flows (MA's "fully played" 90% heuristic is confused by the seek-elapsed semantics) and was dropped.

`_is_at_natural_end_of_track` now an instance method with a fallback path: when `queue.current_item` has been cleared by MA's "End of queue reached", falls back to `_handoff_last_playing_elapsed_ms` (the snapshot captured during real PLAYING ticks) vs `_best_duration_ms()`. Catches the case where MA clears the single-track queue right after stream end.

### Added — IDLE-resume guards

`_apply_idle_resume` (and the dispatcher routing it):
- Skips routing when `_expected_phase ∈ {PAUSED, ENDING}` — PAUSED protects against a stale `paused=False` echo on a deliberately-paused player; ENDING protects against re-issuing REPLACE on the OLD track URI right after a natural-end signal (queue.state IDLE on old URI but Ynison is mid-broadcast of the new track).
- Calls `_cancel_pending_play_media()` before issuing the new REPLACE — honors the cancel-on-track-change invariant from CLAUDE.md (the 8s `_re_issue_debounce_until` window is not a hard guarantee against concurrent REPLACEs on slow `play_media`).
- Wraps the post-REPLACE seek in best-effort `with suppress(Exception)`: a transient seek failure no longer rolls back the windows after the stream is already running.

### Added — Drift-seek guard for cleared queue

`_apply_same_track_sync` skips drift-seek detection when `queue.current_item is None`. After `_signal_track_completion` sends `progress=duration`, MA's queue clears; without this guard the drift detector saw `Ynison=duration` vs `MA=0` and tried to seek the empty queue, throwing exceptions.

### Added — Activation window timing fixes

- `_drift_suppress_until` / `_re_issue_debounce_until` / `_expected_phase` are set BEFORE awaiting `play_media` (MA fires PLAYER_UPDATED while the call is still resolving; without the windows pre-set, those events leaked stale `paused=True` echoes and triggered duplicate-REPLACE races).
- `_apply_track_change` rolls back the optimistic window/phase state on **both** `Exception` and `CancelledError`. Cascaded cancellations could otherwise leave `_expected_phase = ACTIVATING` permanently, with the resolver forcing `paused=False` indefinitely.
- `same_uri_paused` resume in `_apply_track_change` opens a short drift-suppress window so post-resume drift detection doesn't fire on stale Ynison progress.

### Changed — Paused resolver priority

Heartbeat / `_on_ma_player_event` paused resolver order:
1. `_expected_phase == PAUSED` → `paused=True` (user pause is authoritative).
2. `_expected_phase == ACTIVATING` → `paused=False` (don't leak transient IDLE during slow `play_media`).
3. Activation window (`_drift_suppress_until > now`) → `paused=False`.
4. `queue.state != PLAYING` → `paused=True`.

`_handoff_pause` echoes `paused=True` to Ynison immediately and bumps the heartbeat watermark so the next heartbeat tick doesn't race the user's pause with stale `paused=False`.

### Changed — Always REPLACE on same-URI resume

Same-URI resume routes through `_apply_idle_resume` (REPLACE) for both `IDLE` and `PAUSED` queue states. `cmd_play` worked only when the HTTP stream was still live; local web (Chrome) and Chromecast players close the stream after a few seconds of pause and `cmd_play` then has nothing to resume from. REPLACE is slower (3-5s startup) but reliable.

### Refactored — Tests

- 283 tests pass (up from 274 in v2.0). Includes:
  - `TestSharedHelpers` (12 cases): drift threshold edges, queue-rebuild detection, max-position picker, equal/zero edges, forward-stale variants (kept simple after revert).
  - `TestHandoffPause` / `TestHandoffActivate` / `TestHandoffIdempotency` updated to assert against `players.cmd_pause` / `players.cmd_play`.
  - `TestOnMaPlayerEvent` rewritten for state-transition + `_is_at_natural_end_of_track` fallback semantics.
  - Mid-track activation seek path covered.

## [2.0.0] - 2026-05-08

### Architectural refactor — handoff state-sync foundations

This release replaces the temporal echo-detection heuristic and the implicit
single-flag handoff state with strictly causal mechanisms inspired by Spotify
Connect Dealer / librespot, Cast SDK `idleReason`, and MPRIS `SetPosition`
context binding. The goal is *deterministic* two-way sync between the Yandex
Music app and Music Assistant — no more "echo blocked my pause", no more
"reconnect cascaded a stale pause to the active phone", no more "rapid
toggle restarted the track at 0".

### Added — Lamport-style version-counter echo (`provider/ynison_client.py`)

- `YnisonClient` now stamps each outbound state with a monotonic version
  derived from `time.time_ns()` and tracks two watermarks
  (`_pending_outbound_queue_version`, `_pending_outbound_status_version`).
  An incoming state is classified as our echo only when **both** the queue
  and status version blocks are authored by us **and** their inbound
  versions are `<=` our latest pending watermark. Replaces the previous
  device-id-only AND check, which still false-flagged peer state changes
  whenever the heartbeat had recently bumped the queue version.
- `_classify_state_as_echo` and `_block_is_our_echo` helpers; new
  `_capture_outbound_versions` records the watermark on every send path
  (`update_player_state`, `send_full_state`, `update_playing_status`).

### Added — Reconnect settle window + fresh state (`provider/ynison_client.py`)

- `_post_reconnect_settle_until` (2 s) opens after each `_connect_state`.
  `_handle_ynison_state` early-returns inside this window so the first
  Ynison broadcast after reconnect (which may carry pre-reconnect state
  from another peer) does not trigger spurious play/pause/seek commands
  in MA.
- `_connect_state` now sends a **fresh** initial state on reconnect via
  `send_full_state()` (no argument), instead of replaying
  `self.state.player_state` — the previous behaviour rebroadcast a
  paused-from-30s-ago snapshot to peers and made the phone go silent.
- New `in_post_reconnect_settle` property exposed for the provider check.

### Added — Explicit handoff phase (`provider/provider.py`)

- New `HandoffPhase` enum (`IDLE`, `ACTIVATING`, `PLAYING`, `PAUSED`,
  `ENDING`) and `_expected_phase` field. The plugin now records *what it
  thinks the player should be doing*, separately from MA queue's actual
  state. This disambiguates `(queue.state == IDLE, expected == ENDING)`
  (signal completion) from `(queue.state == IDLE, expected == PAUSED)`
  (watchdog quirk, do not advance) — the underlying cause of the original
  cascade.
- `_handoff_activate` sets `ACTIVATING` after a successful `play_media`;
  `_on_ma_player_event` transitions `ACTIVATING/PAUSED` → `PLAYING` on
  the first PLAYING tick; `_handoff_pause` sets `PAUSED`.

### Added — Idempotency cache + cancel-on-track-change

- `_idempotent(action, key)` helper with a 1 s TTL window. Duplicate
  pause / play_media commands inside the window are no-ops, preventing
  Ynison-echo storms from issuing the same MA command 2-3 times back to
  back. Used in `_handoff_pause` (key=player_id) and `_handoff_activate`
  new-track branch (key=track_id).
- `_cancel_pending_play_media()` cancels a still-running `play_media`
  task before issuing a new one. Rapid `next` taps in the Yandex app
  used to fire several back-to-back, and a half-finished load racing
  the new one confused MA's queue runner.
- New field `_play_media_task: asyncio.Task | None` and a 3-tier backoff
  constant `_PLAY_MEDIA_BACKOFF_SECONDS = (1.0, 2.0, 5.0)` for future use.

### Changed — split former `_handoff_grace_until` into two semantics

- `_drift_suppress_until` — set after a `play_media(REPLACE)` or `seek`,
  blocks spurious drift-seek detection until MA's stream actually starts.
  Previously conflated with the re-issue debounce, leading to double
  play_media calls on rapid pause/play.
- `_re_issue_debounce_until` — set after issuing `play_media`, blocks
  another REPLACE for `_REISSUE_DEBOUNCE_PERIOD = 3.0` seconds. Solves
  the IDLE-resume re-issue loop where each `paused=False` echo would
  fire another REPLACE before MA had transitioned to PLAYING.
- New constants `_DRIFT_SUPPRESS_PERIOD = 5.0`, `_REISSUE_DEBOUNCE_PERIOD
  = 3.0`, `_COMMAND_IDEMPOTENCY_TTL = 1.0`.

### Renamed

- `_handoff_current_track_id` → `_expected_track_id` (clearer ownership
  semantics — *we* expect this; MA queue is the cache).

### Tests

- `tests/test_provider_handoff.py`: new classes
  `TestHandoffIdempotency`, `TestHandoffCancelTask`,
  `TestHandoffFsmTransitions` (9 cases). Covers pause idempotency
  within/after TTL, play_media dedup, cancellation of pending
  play_media, ACTIVATING→PLAYING transition on first MA PLAYING tick,
  PAUSED phase set after pause, phase preserved on pause failure.
- `tests/test_ynison_client.py`: `test_reconnect_sends_fresh_state_no_stale_replay`
  (regression for stale rebroadcast), `test_cold_start_does_not_arm_settle_window`,
  echo classification tests under the new Lamport scheme.

### Known status

- Full FSM-driven dispatch (decision matrix, `_apply_track_change` /
  `_apply_pause` / `_apply_play` / `_apply_seek` / `_apply_completion`
  with parametrized routing) is **deferred** to a follow-up release —
  v2.0 introduces the bookkeeping fields (`_expected_phase`,
  `_expected_track_id`, idempotency cache, separated grace fields) and
  the Lamport echo / settle-window primitives that make the dispatch
  safely possible. Existing handlers continue to inline their decisions
  with the new fields, which already eliminates the four critical race
  conditions (echo / reconnect cascade / rapid-toggle restart /
  duplicate play_media).
- The `_PLAY_MEDIA_BACKOFF_SECONDS` constant is wired but the retry
  loop itself is intentionally not yet activated — exception-driven
  re-issue should be observed once before being automated. Manual
  recovery by waiting for the next Ynison state still works.

## [1.9.1] - 2026-05-08

### Fixed
- **Handoff: spurious advance after pause on single-track queue.** When the user pressed pause (either in the Yandex Music app or in the MA UI), MA's queue runner reported `IDLE` shortly afterwards because the REPLACE-pushed queue had no upcoming items. The plugin's `_on_ma_player_event` interpreted that IDLE as natural end-of-track and signalled completion to Ynison, which advanced through the RADIO tail and started a cascade of `play_media` calls. Now `_on_ma_player_event` only signals completion when `corrected_elapsed_time >= duration - 5s` (new helper `_is_at_natural_end_of_track`); shorter elapsed values are treated as pause/stop and leave the marker untouched. Conservative on unknown duration / missing `current_item` (does not signal). Live-reproduced and confirmed: pause from Ynison-app and from MA UI both no longer trigger the cascade.
- **Handoff: heartbeat kept ticking after another device took over.** The `_clear_active_player` branch in `_handle_ynison_state` was gated on `_source_details.in_use_by`, which is always None in handoff (no `AUDIO_SOURCE`). Result: when Ynison re-balanced the active device to the phone, `_active_player_id` stayed set and the heartbeat continued pushing stale MA queue progress to Ynison every 5s. Branch now also fires on `_is_handoff and _active_player_id`.
- **Handoff: heartbeat reported `paused=False` while MA queue was IDLE/PAUSED.** `is_paused` was computed as `queue.state == PAUSED` — anything else (including IDLE after watchdog) was reported as "playing" to Ynison, which made the Yandex Music app show "playing" with no audio. Changed to `is_paused = queue.state != PLAYING`, so IDLE/PAUSED/UNKNOWN all surface as paused.
- **Handoff: pause→play in the app could restart the track at 0.** When the queue went IDLE between toggle clicks, IDLE-resume issued `play_media(REPLACE) + seek(state.progress_ms)` — but Ynison's `progress_ms` echo lagged the toggle, so the seek argument was 0. Now we snapshot `corrected_elapsed_time` while `queue.state == PLAYING` (`_handoff_last_playing_elapsed_ms`) and prefer that over Ynison's stale progress.
- **Handoff: rapid pause/play could trigger many `play_media(REPLACE)` calls per second.** The IDLE-resume branch was unguarded. Added a debounce gate: while `_handoff_grace_until > now`, additional re-issue calls are dropped — MA gets the time it needs to spin up the stream.
- **Handoff: echo OR-logic silenced legitimate peer actions.** `_parse_state` flagged a state as echo when *either* `player_queue.version` *or* `status.version` was authored by us. A peer (phone) toggling pause produced a state where `status.version=peer` but `player_queue.version` was still ours from the last heartbeat → wrongly classified as echo, and `_handoff_activate` skipped the response. Switched to AND-logic: state is echo only when **both** version-blocks are ours.

### Tests
- New `tests/test_provider_handoff.py::TestOnMaPlayerEvent` cases:
  - `test_idle_queue_at_pause_does_not_signal_completion` (regression for the cascade bug);
  - `test_idle_queue_with_unknown_duration_does_not_signal` (conservative behaviour);
  - `test_idle_queue_without_current_item_does_not_signal`;
  - `test_idle_short_track_is_treated_as_near_end` (sub-5s tracks always signal on IDLE).
- Updated `test_idle_queue_signals_completion_once` to set `current_item.duration` and `corrected_elapsed_time` so it reaches the near-end branch.
- New `tests/test_ynison_client.py::TestParseState` cases for AND-echo:
  - `test_echo_flag_true_only_when_both_authors_ours` (positive case);
  - `test_echo_flag_false_when_only_queue_is_ours` (regression for the OR bug);
  - `test_echo_flag_false_when_only_status_is_ours` (mirror case).
- Renamed/restructured the older OR-flavoured echo tests.

### Known limitations (carried into v2.0 refactor)
- **Quick pause→play toggles can still occasionally restart the track.** The MA single-track queue does not expose a true "pause without watchdog stop"; under fast toggles the queue may transition through IDLE faster than our 3s debounce, causing a re-issue with whatever offset was last snapshotted. The full architectural fix lives in v2.0 (FSM-driven dispatch, idempotent commands, cancel-on-track-change).
- **30-second pause watchdog**: `mass.player_queues.pause()` in MA core stops the queue (`IDLE`) 30s after pause to release the renderer. After that point we can't simply `play()` the queue — we re-issue `play_media(REPLACE)` with the saved offset. There is a short audible gap while MA spins up the stream again. v2.0 keeps the same approach but inside an explicit FSM so the decision is auditable.
- **Seek can fail with `MediaNotFoundError`** for individual tracks when MA's `player_queues.seek()` triggers a stream re-resolve and `yandex_music` returns "not available" (track moderated, geo-restricted, or token expired). The plugin logs `Handoff seek failed on <player>` and leaves Ynison/MA in their current positions. Workaround: wait until the next track or re-pick the source in the Yandex app. Mitigation belongs in `yandex_music`, not in this plugin.
- **`Late binary: skipping N chunk(s)`** warnings can still appear when MA's outer ffmpeg upsamples a 16-bit AAC track inside a session frozen on `s24le` (first lossless track). Fundamentally tied to the session-frozen `PluginSource.audio_format` model — use `playback_mode: handoff` or restart the queue if the warnings get loud.

## [1.9.0] - 2026-05-08

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
- **Handoff pause uses `_active_player_id` only**, never `_get_target_player_id()` (Copilot review N1). Falling back to auto-select after startup/cleanup could pause an unrelated MA queue.
- **`_clear_active_player()` resets `_handoff_last_progress_sync_mono`** along with the rest of the handoff bookkeeping (Copilot review N2). Previously a stale watermark could throttle the first progress/heartbeat update of a fresh activation.
- **`_handoff_activate` only starts the heartbeat after a successful dedup/resume/play_media commit** (Copilot review N3). Previously the heartbeat was scheduled even when `play_media` raised, causing it to push stale MA queue progress to Ynison and delay rebalancing away from a non-working device.

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
