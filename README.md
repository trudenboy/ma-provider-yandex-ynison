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

**Beta** (v2.2.9) — see [CHANGELOG.md](CHANGELOG.md) and [ROADMAP.md](ROADMAP.md).

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
| `provider/__init__.py` | Setup function and `SUPPORTED_FEATURES` |
| `provider/provider.py` | `YandexYnisonProvider(PluginProvider)` — main plugin class |
| `provider/setup_flow.py` | Native setup/reconfigure flow for account and device identity |
| `provider/credential_source.py` | Read-only access to linked Yandex Music setup credentials |
| `provider/ynison_client.py` | `YnisonClient` — WebSocket client for Ynison protocol |
| `provider/streaming.py` | PCM normalization profiles, ffmpeg pacing args |
| `provider/protocols.py` | `YandexMusicProviderLike` — structural Protocol for yandex_music dependency |
| `provider/auth.py` | Temporary music-token refresh via `ya-passport-auth` |
| `provider/config_helpers.py` | Configured Yandex Music instance discovery |
| `provider/constants.py` | URLs, config keys, defaults, timeouts |
| `provider/manifest.json` | Plugin metadata (`multi_instance: true`, `depends_on: yandex_music`) |

## Configuration

### Authentication

Every Ynison instance links to one configured `yandex_music` provider.
Yandex Music is the only persistent owner of OAuth credentials; Ynison reads
its current `token` and `x_token` from encrypted setup data. When only an
`x_token` is available, Ynison may mint a temporary in-memory music token at
startup; it also refreshes that token after an authentication rejection. To use
another Yandex account, configure another Yandex Music provider instance and
link Ynison to it.

| Parameter | Type | Description |
|-----------|------|-------------|
| **Yandex Music account** | Dropdown | Required configured `yandex_music` provider instance whose account Ynison uses |

Ynison never persists or rotates linked credentials. Secret values are unwrapped
only within the local authentication path, including the bounded in-memory
refresh cache and Ynison authorization header construction.

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
