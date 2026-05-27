---
id: "0003"
title: "Surface Ynison send failures to delivery-critical callers"
size: L
status: inprogress
priority: P1
effort_minutes: 60
---

## Problem Statement

When the Ynison WebSocket is in a transient bad state (mid-reconnect, half-closed socket, `aiohttp.ClientError` on a `send_str`), `YnisonClient._send` logs a warning, schedules a reconnect, and returns normally. Five delivery-critical callers cannot tell the send was dropped:

- **`_signal_track_completion`** — end-of-track signal. If lost, Ynison never sees the track finished and the YM app sits on the played track until reconnect-broadcast catches up (often 5–60 s).
- **`_advance_queue_index`** — queue advance after natural track end. If lost, `_wait_for_track_change` blocks for its full 30 s timeout, then stops the stream.
- **`_on_play`, `_on_pause`, `_on_seek`** — user commands. If lost, MA's UI shows the command as succeeded while the Yandex Music app keeps the old state. The MA contract here is to raise `PlayerCommandFailed` so the user sees a clear failure.

Heartbeat callers (`_sync_progress`, `_update_metadata_from_stream`, `_update_queue_list`) are correctly fire-and-forget — the next iteration re-syncs — so they must keep their existing silent-recovery behaviour.

## Solution Summary

Introduce a `strict: bool = False` opt-in on `YnisonClient._send`, `update_playing_status`, and `update_player_state`. When `strict=True`, transport failures raise a new `YnisonSendError(ConnectionError)` instead of being silently swallowed; the reconnect is still scheduled. Delivery-critical callers opt in and translate to `PlayerCommandFailed` (user-command path) or log-and-return (auto-advance / completion path). Heartbeat callers keep the default `strict=False`. Also extract the duplicated reconnect-task scheduling block (`_message_loop` and `_send`) into a `_schedule_reconnect` helper.

## Acceptance Criteria

1. New `YnisonSendError(ConnectionError)` exception class exported from `provider.ynison_client`.
2. `YnisonClient._send(msg, *, strict=False)` — on disconnect or transport error, raises `YnisonSendError` only when `strict=True`; default behaviour unchanged.
3. `update_playing_status(..., strict=False)` and `update_player_state(..., strict=False)` accept and forward `strict`.
4. `_send_progress_to_ynison(..., strict: bool = False)` in `provider/provider.py` accepts and forwards `strict` to `update_playing_status`.
5. `_signal_track_completion` calls `_send_progress_to_ynison(strict=True)` and logs a warning on `YnisonSendError` (no reraise — reconnect already scheduled, stream is ending anyway).
6. `_advance_queue_index` calls `update_player_state(strict=True)` and on `YnisonSendError` logs and returns (no reraise — `_wait_for_track_change` handles the stalled-advance fallback).
7. `_on_play`, `_on_pause`, `_on_seek` pass `strict=True` and catch `YnisonSendError`, raising `PlayerCommandFailed` from it. For `_on_seek`, neither `_seek_position_ms` nor `_seek_grace_until` are mutated on a failed send (state stays consistent).
8. `_sync_progress`, `_update_metadata_from_stream`, `_update_queue_list` do **not** pass `strict=True`; existing behaviour is preserved (regression-tested).
9. `_schedule_reconnect()` helper replaces the two existing `if not stop_event...: _reconnect_task = create_task(...)` blocks; only one reconnect task can be live at a time.

## Test Plan

### `tests/test_ynison_client.py`
- `test_send_strict_raises_ynison_send_error_when_disconnected` — `_ws=None`, `strict=True` → raises.
- `test_send_strict_raises_on_client_error_and_schedules_reconnect` — `send_str` raises `aiohttp.ClientError`, `strict=True` → raises AND reconnect scheduled.
- `test_send_non_strict_swallows_and_schedules_reconnect` — same fault, default `strict` → no raise, reconnect scheduled (regression guard for existing behaviour).
- `test_update_playing_status_forwards_strict_kwarg` — calls with `strict=True` → `_send` receives `strict=True`.
- `test_update_player_state_forwards_strict_kwarg` — same.
- `test_schedule_reconnect_idempotent_when_task_alive` — concurrent calls during a live reconnect task → only one task created.

### `tests/test_provider.py`
- `test_on_play_raises_player_command_failed_when_send_fails`
- `test_on_pause_raises_player_command_failed_when_send_fails`
- `test_on_seek_raises_player_command_failed_when_send_fails` + asserts `_seek_position_ms` unchanged on failure.
- `test_signal_track_completion_logs_on_send_failure` — `update_playing_status.side_effect = YnisonSendError`; assert no raise, warning logged.
- `test_advance_queue_index_returns_on_send_failure` — assert no raise, returns cleanly.
- `test_sync_progress_unchanged_on_send_failure` — non-strict heartbeat keeps ticking.

### Sequence diagram

```
User pauses in MA UI
  │
  ▼
on_source_control(PAUSE) ──► _on_pause
                              │  (idempotency check)
                              ▼
                              _send_progress_to_ynison(strict=True)
                              │
                              ▼
                              update_playing_status(strict=True)
                              │
                              ▼
                              _send(strict=True)
                                 │
                                 ├── ws ok ──► success, return
                                 │
                                 └── ws bad ──► schedule_reconnect()
                                                 │
                                                 └── raise YnisonSendError
                                                       │
                                                       (catch in _on_pause)
                                                       │
                                                       ▼
                                                       raise PlayerCommandFailed
                                                       (MA shows error toast)
```

### Manual

- Run MA dev server; pause/play from Yandex Music app while local network is briefly down; confirm MA UI surfaces a failure toast on the command instead of silently accepting.
