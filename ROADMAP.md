# Roadmap

## Current: v1.2.0 (Beta)

Released features:
- Ynison protocol integration (play/pause/next/prev/seek)
- Multi-instance support with token sharing
- Ya-passport-auth migration
- Duration and progress sync
- Reconnect with exponential backoff
- SyncStateFromEOV queue replenishment on queue exhaustion

## Short-term

### PR #3614 — upstream merge
- Address remaining CI and review feedback
- Get merged into `music-assistant/server`

### Queue replenishment improvements

The Ynison protocol doesn't natively auto-replenish radio queues when a
non-YM-app device is the active player. We currently send `SyncStateFromEOV` to
request the backend to refresh the queue from the centralized EOV service.

**Additional strategies (to evaluate if EOV sync alone is insufficient):**

1. **Proactive progress updates** — send `update_playing_status` at ~90% of
   track progress to trigger the YM app's pre-fetch logic, even when
   our device is active. Low risk, easy to implement.

2. **Direct rotor REST API** — call `/rotor/station/{station}/tracks` ourselves
   to fetch the next batch of radio tracks, then push them into the Ynison
   queue via `update_player_state`. High complexity: requires station tracking,
   feedback API calls, and queue version management.

3. **Hybrid approach** — SyncStateFromEOV first → proactive progress fallback →
   rotor API last resort. Progressively more effort but maximum reliability.

## Medium-term

### `ya-ynison` — standalone Ynison library
Extract `ynison_client.py` into a reusable Python package on PyPI.

**Motivation:**
- Currently no Python library for the Ynison protocol exists
- Our client is nearly standalone (single MA import: `LoginFailed`)
- Enables reuse: standalone Linux players, Discord RPC, IoT devices
- Simplifies testing (no MA dependencies)

**Scope:**
- `YnisonClient` — async WebSocket client (connect, state sync, playback control)
- `YnisonDeviceInfo`, `YnisonState`, `PlayerState` — data models
- Custom exceptions (`YnisonAuthError`, `YnisonConnectionError`)
- Accept `aiohttp.ClientSession` externally (no framework coupling)
- Package name: `ya-ynison`

**Steps:**
1. Create `ya-ynison` repository with proper packaging (pyproject.toml, CI)
2. Move and refactor `ynison_client.py` — replace `LoginFailed` with own exceptions
3. Publish to PyPI
4. In this plugin: replace inline client with `from ya_ynison import YnisonClient`

### Multi-player per instance (server API)
Expose multiple MA players from a single provider instance without duplicating configs.

**Approach A (preferred):** Server-side `get_sources()` API
- Add `get_sources() -> list[PluginSource]` to `PluginProvider` base class
- Requires separate PR in `music-assistant/server`
- Plugin manages `Dict[player_id → PlayerContext]`

**Approach B (fallback):** Auto child instances
- If server API change is rejected
- Master config auto-creates child provider instances per player
- Works with current API but adds complexity

## Long-term

### Standalone Ynison player for embedded Linux
Lightweight daemon using `ya-ynison` + ALSA for devices like Luckfox Max / PureFox.

- Register as Ynison device visible in Yandex Music app
- Receive playback commands, fetch and play audio via ALSA/I2S
- Minimal footprint: Go or Python, suitable for 256 MB RAM boards
- Depends on: `ya-ynison` library extraction
