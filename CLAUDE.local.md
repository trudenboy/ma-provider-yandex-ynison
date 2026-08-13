# CLAUDE.local.md

Provider-specific architecture, key flows, and gotchas for the Yandex Music Connect (Ynison) provider.

## Known Technical Debt

### AudioSource Lifecycle Contract Mismatch

**Status**: Temporary workaround in place (v4.1.2+)

Music Assistant's AudioSource lifecycle (`controllers/streams/controller.py:719`, `:1567`) currently catches only `RuntimeError` for clean stream abort. When player switching is disabled, `on_source_selected` must abort the stream to prevent a wrong-player selection from proceeding.

**Current solution**: Raise `RuntimeError` instead of the more specific `ActionUnavailable` from `music_assistant_models.errors`.

**Upstream fix required**: Update MA's streams controller to accept both `RuntimeError` and `ActionUnavailable` (and ideally any `MusicAssistantError` subclass) in the audio-source lifecycle handlers. See [music-assistant/server#5589](https://github.com/music-assistant/server/pull/5589#discussion_r3794988694).

**Related code**:
- `provider/provider.py:719` — temporary `RuntimeError` with inline NOTE
- `tests/test_provider.py` — test cases use `RuntimeError` until contract updates

## Architecture

Yandex Ynison provider maintains an exclusive AudioSource and coordinates playback between Yandex Music clients and Music Assistant players via persistent WebSocket.

### Dynamic Stream Sessions

Maximum-quality mode (`STREAM_MODE_MAX_QUALITY`) prefetches each track's real format and restarts the AudioSource only when the effective PCM signature (content type, sample rate, bit depth, channels) changes for the actual player.

Key invariants:
- Format selection happens in `on_source_selected` after MA has fixed `StreamDetails`
- Same-format track transitions preserve the Ynison playback position
- Failed launches restore retryable state by clearing `_dynamic_target_track_id`
