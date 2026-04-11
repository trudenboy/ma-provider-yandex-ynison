# Roadmap

## Current: v1.2.0 (Beta)

Released features:
- Ynison protocol integration (play/pause/next/prev/seek)
- Multi-instance support with token sharing
- Ya-passport-auth migration
- Duration and progress sync
- Reconnect with exponential backoff

## Short-term

### PR #3614 — upstream merge
- Address remaining CI and review feedback
- Get merged into `music-assistant/server`

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
