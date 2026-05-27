---
id: "0005"
title: "Extract connected-Ynison guard, fix drift docstring, rename `_paused`"
size: M
status: inprogress
priority: P2
effort_minutes: 18
---

## Problem Statement

Three small maintainability nits surfaced during the spec-0003 review:

1. **Duplicated guard.** `_on_play`, `_on_pause`, `_on_next`, `_on_previous`,
   `_on_seek` open with the same five lines — `if not self._ynison: raise
   UnsupportedFeaturedException("Ynison client not initialized"); if not
   self._ynison.connected: raise PlayerCommandFailed("Ynison WebSocket
   disconnected")`. Any future change to the guard has to touch five sites.

2. **Misleading docstring.** `_classify_drift` claims "drift below
   ``threshold_ms``" while the code is `<=`. The off-by-one drift class
   ("ignore" vs "seek") is testable, so the doc rot is real.

3. **Confusing field name.** `self._paused: bool` is set only in
   `_pause_playback` (i.e. when *Ynison* paused us externally) and read in
   `_activate_playback` to decide whether to re-issue `play_media`. The name
   reads as the global playback state — clearer as `_externally_paused`.

This work is stacked on top of spec 0003 because (1) collides with the
strict-mode edits in `_on_play` / `_on_pause` / `_on_seek` from that PR.

## Solution Summary

Introduce a `_require_connected_ynison(self) -> YnisonClient` helper that
returns the live client or raises the appropriate exception. Replace the
five duplicated guard blocks. Tighten the `_classify_drift` docstring to
match the `<=` check. Rename `_paused` → `_externally_paused` (4 in-file
references plus 6 test references and 1 test method name).

## Acceptance Criteria

1. New `_require_connected_ynison()` method raises
   `UnsupportedFeaturedException("Ynison client not initialized")` when
   `self._ynison is None` and `PlayerCommandFailed("Ynison WebSocket
   disconnected")` when `self._ynison.connected is False`. Otherwise returns
   `self._ynison` (typed `YnisonClient`).
2. The five command handlers (`_on_play`, `_on_pause`, `_on_next`,
   `_on_previous`, `_on_seek`) call the helper instead of inlining the
   guard. Existing exception messages are preserved verbatim so existing
   `pytest.raises(..., match=...)` tests keep passing.
3. `_classify_drift` docstring reads "at or below ``threshold_ms``" (one
   word: code is `<=`).
4. Field `self._paused` renamed to `self._externally_paused`. Every
   provider.py reference (5 sites) updated. Tests in `tests/test_provider.py`
   updated (6 field references + 1 method-name rename
   `test_resume_via_paused_flag_alone` → `test_resume_via_externally_paused_flag_alone`).
5. No reference to the YnisonState property `state.is_paused` is touched
   (different attribute on a different object).
6. All existing tests pass; 3 new tests added for the helper.

## Test Plan

- `test_require_connected_ynison_raises_unsupported_when_client_missing` —
  `provider._ynison = None`, expect `UnsupportedFeaturedException`.
- `test_require_connected_ynison_raises_command_failed_when_disconnected` —
  `provider._ynison.connected = False`, expect `PlayerCommandFailed`.
- `test_require_connected_ynison_returns_client_when_ready` — happy path
  returns the same identity as `self._ynison`.
- Existing `test_on_*_no_ynison_raises` regression coverage continues to
  pass (the new helper preserves the original messages).
- `uv run pytest` green; `uv run pre-commit run --all-files` clean.

### Sequence

```
on_source_control(PAUSE) ──► _on_pause
                              │
                              ▼
                              client = _require_connected_ynison()
                              │
                              ├── _ynison is None ──► raise UnsupportedFeaturedException
                              │
                              ├── _ynison.connected is False ──► raise PlayerCommandFailed
                              │
                              └── return client ──► ... rest of _on_pause
```
