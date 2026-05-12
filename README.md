# Yandex Music Connect (Ynison) — Music Assistant Plugin


<!-- >>> ma-provider-tools sync (readme header) — DO NOT EDIT >>> -->
[![CI](https://github.com/trudenboy/ma-provider-yandex-ynison/actions/workflows/test.yml/badge.svg)](https://github.com/trudenboy/ma-provider-yandex-ynison/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/trudenboy/ma-provider-yandex-ynison?display_name=tag)](https://github.com/trudenboy/ma-provider-yandex-ynison/releases/latest)
[![License](https://img.shields.io/github/license/trudenboy/ma-provider-yandex-ynison)](LICENSE)
[![Music Assistant](https://img.shields.io/badge/Music%20Assistant-9070B8?logo=python&logoColor=white)](https://www.music-assistant.io/)[![stable](https://img.shields.io/endpoint?url=https%3A%2F%2Ftrudenboy.github.io%2Fma-provider-tools%2Fbadges%2Fyandex_ynison-stable.json)](https://github.com/music-assistant/server/releases/latest)[![beta](https://img.shields.io/endpoint?url=https%3A%2F%2Ftrudenboy.github.io%2Fma-provider-tools%2Fbadges%2Fyandex_ynison-beta.json)](https://github.com/music-assistant/server/releases?q=prerelease)
[![Stars](https://img.shields.io/github/stars/trudenboy/ma-provider-yandex-ynison?style=flat&logo=github)](https://github.com/trudenboy/ma-provider-yandex-ynison/stargazers)

**📖 [Documentation / Документация](https://trudenboy.github.io/ma-provider-yandex-ynison/)** · **🔄 [Changelog / Журнал](CHANGELOG.md)** · **🐛 [Issues / Проблемы](https://github.com/trudenboy/ma-provider-yandex-ynison/issues)** · **💬 [Discussions / Обсуждения](https://github.com/trudenboy/ma-provider-yandex-ynison/discussions)**

**Related providers:** [Yandex Music](https://github.com/trudenboy/ma-provider-yandex-music)
<!-- <<< ma-provider-tools sync (readme header) <<< -->

Makes any Music Assistant player appear as a playback device in the official
Yandex Music app via the Ynison protocol (Yandex's equivalent of Spotify
Connect).

## How it works

1. Plugin connects to Yandex's Ynison service via WebSocket
2. Your MA player appears as a device in the Yandex Music app
3. Select the device in Yandex Music → audio streams through MA to your speaker
4. Control playback from the Yandex Music app (play/pause/skip/seek)

## Status

**Beta** (v2.2.1) — see [CHANGELOG.md](CHANGELOG.md) and [ROADMAP.md](ROADMAP.md).

## Architecture

```
Yandex Music app (phone/web/desktop)
  │
  ▼
Ynison WebSocket  ◄──►  YnisonClient (ynison_client.py)
  │                         │  two-step: Redirector → State Service
  ▼                         │  JSON over WebSocket (gRPC-like framing)
YandexYnisonProvider (provider.py)
  │
  ├─ receives track_id from Ynison PlayerState
  ├─ resolves StreamDetails via linked yandex_music provider
  ├─ fetches audio from Yandex CDN (raw or encrypted FLAC/MP3/AAC)
  ├─ per-track ffmpeg → fixed PCM (s16le or s24le)
  │
  ▼
PluginSource → MA Player (Chromecast / DLNA / AirPlay / etc.)
  │
  └─ on play/pause/seek/next/prev → update_playing_status back to Ynison
```

### Passive player model

MA acts as a **passive player** — Yandex Music controls the queue. The plugin
never manipulates `current_playable_index` on auto-advance. When a track
finishes, the plugin signals completion via `update_playing_status` and waits
for the Yandex app (or Ynison backend) to push the next track. The only
exception is RADIO/wave queues, where the active device is responsible for
replenishing tracks via the Yandex Music REST API.

### Audio streaming pipeline

Each track is decoded through its own **per-track ffmpeg** process to produce
a fixed PCM output that matches the session format. This ensures MA's single
outer ffmpeg never encounters mid-stream format changes.

```
Yandex CDN → raw audio (FLAC/MP3/AAC)
  → ffmpeg (per-track, realtime pacing)
  → PCM s16le@44.1kHz or s24le@48kHz (based on quality tier)
  → yield chunks via get_audio_stream()
  → MA outer ffmpeg → target player
```

The PCM format is **frozen at session start** — if the normalization format
changes mid-session (e.g. provider reload), the new format applies only to the
next session, preventing bit-depth/sample-rate mismatches.

### Ynison echo detection

After the plugin sends `update_playing_status`, Ynison echoes the value back
within a few seconds. Without detection, these echoes trigger false seek events.
The plugin tracks the last sent progress and timestamp, treating any incoming
value within ±2 s / 5 s window as an echo to be ignored.

### Radio queue replenishment

Ynison only syncs playback state — it does **not** auto-generate new tracks for
radio/wave queues when a non-YM-app device is active. The plugin handles this
by calling `get_rotor_station_tracks()` on the linked yandex_music provider when
nearing the end of the queue, then pushing the expanded list to Ynison via
`update_player_state`.

## Key modules

| File | Purpose |
|------|---------|
| `provider/__init__.py` | Setup function, config entries, `SUPPORTED_FEATURES` |
| `provider/provider.py` | `YandexYnisonProvider(PluginProvider)` — main plugin class |
| `provider/ynison_client.py` | `YnisonClient` — WebSocket client for Ynison protocol |
| `provider/streaming.py` | PCM normalization profiles, ffmpeg pacing args |
| `provider/protocols.py` | `YandexMusicProviderLike` — structural Protocol for yandex_music dependency |
| `provider/yandex_auth.py` | QR authentication and token refresh via `ya-passport-auth` |
| `provider/config_helpers.py` | Sibling instance token discovery |
| `provider/constants.py` | URLs, config keys, defaults, timeouts |
| `provider/manifest.json` | Plugin metadata (`multi_instance: true`, `depends_on: yandex_music`) |

## Configuration

### Authentication

The plugin supports two top-level auth modes, picked via the **Yandex Music
source** dropdown:

* **Borrow** (default when a `yandex_music` MusicProvider exists) — read
  OAuth credentials from a linked `yandex_music` instance. Token storage and
  scheduled refresh stay with that provider; this plugin only does
  in-memory refresh on 401.
* **Own credentials** — populate this instance's own credentials. Two ways
  to fill them:
  * **Login with QR code** — opens a QR popup; scan with the Yandex app and
    the music token + session token are stored automatically.
  * **Manual paste** — enter a Yandex Music OAuth token by hand (escape
    hatch for headless setups).

Use *Own credentials* with QR to bind separate MA players to separate
Yandex accounts (one plugin instance per player) without spinning up
multiple `yandex_music` providers.

| Parameter | Type | Description |
|-----------|------|-------------|
| **Yandex Music source** | Dropdown | Borrow from a configured `yandex_music` instance, or use this instance's own credentials |
| **Login with QR code** | Action | Own mode only. Opens a QR popup; scan with the Yandex app to populate the token automatically |
| **Remember session** | Boolean (default: `true`) | Own mode only. When enabled, stores a long-lived `x_token` so the plugin can refresh the music token on 401. Disable to keep only the short-lived music token (re-QR on expiry) |
| **Reset authentication** | Action | Own mode only. Clears the music token, session token, and stored login |
| **Yandex Music Token** | Secure string | Own mode only. Auto-populated by QR; can also be filled manually |

Tokens are `SecretStr` throughout the codebase; `get_secret()` is only
called at two sites: `perform_qr_auth` (extracting plain strings from the
Passport response for MA config storage) and `YnisonClient._build_headers`
(building the `Authorization: OAuth …` header for the WebSocket handshake).

### Playback

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **Connected MA Player** | Dropdown | `Auto` | Target MA player. `Auto` prefers a currently playing player, falls back to first available |
| **Allow manual player switching** | Boolean | `true` | When enabled, selecting this plugin as a source on any player switches playback to it. When disabled, playback is fixed to the configured player |

### Advanced

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **Output sample rate** | Dropdown | `Auto` | PCM output sample rate. `Auto` selects 44.1 kHz for lossy, 48 kHz for lossless sources. Options: 44100, 48000, 96000 Hz |
| **Output bit depth** | Dropdown | `Auto` | PCM output bit depth. `Auto` selects 16-bit for lossy, 24-bit for lossless. Options: 16, 24 bit |
| **Device name** | String | `Music Assistant` | How this device appears in the Yandex Music app |

### Auto-detection logic

When set to `Auto`, sample rate and bit depth are derived from the linked
yandex_music provider's quality setting:
- `superb` / `lossless` → **24-bit / 48 kHz** (PCM_S24LE)
- all others → **16-bit / 44.1 kHz** (PCM_S16LE)

## Ynison protocol notes

- **Transport**: JSON over WebSocket (gRPC-like framing, not binary protobuf)
- **Two-step connection**: Redirector → State Service
  - Redirect URL: `wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison`
  - State URL: `wss://{host}/ynison_state.YnisonStateService/PutYnisonState`
- **Auth**: `Authorization: OAuth {token}`, device info in `Sec-WebSocket-Protocol` header
- **Reconnect**: exponential backoff (5, 10, 30, 60 s saturating) with ±20% jitter, retries indefinitely
- **Constraint**: Ynison rejects `progress > duration` with error 400030001 and disconnects — progress is always clamped
- **Reference implementations**: [bulatorr/go-yaynison](https://github.com/bulatorr/go-yaynison) (Go), [FozerG/YandexMusicRPC](https://github.com/FozerG/YandexMusicRPC) (Python)

## Development

```bash
# Setup
git clone https://github.com/trudenboy/ma-provider-yandex-ynison.git
cd ma-provider-yandex-ynison
scripts/setup.sh  # or: uv sync --extra test

# Run tests
uv run pytest

# Lint & format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy
```

## License

MIT License. See [LICENSE](LICENSE).
