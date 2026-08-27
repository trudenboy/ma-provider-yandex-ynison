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

Yandex Music Connect makes a Music Assistant player appear as a playback device
in the official Yandex Music app. The app remains the queue owner and remote
control; Music Assistant resolves and delivers the selected tracks to the
configured speaker.

## Status

**Stable.** Release history is available in [CHANGELOG.md](CHANGELOG.md);
remaining work is tracked in [ROADMAP.md](ROADMAP.md).

## Requirements

- A current Music Assistant installation with this provider available.
- At least one configured and authenticated `yandex_music` provider instance.
- A target Music Assistant player.
- Working ffmpeg support in the Music Assistant installation.

Each Ynison instance links to exactly one Yandex Music provider instance. Yandex
Music remains the only persistent owner of OAuth credentials; Ynison reads the
linked account's setup credentials and keeps refreshed music tokens in memory
only. To use several accounts or publish several devices, create a Yandex Music
instance and a Ynison instance for each account/player pairing.

## Architecture

```text
Yandex Music app
  │  queue, active device, play/pause/seek/skip
  ▼
Ynison redirector → Ynison state WebSocket
  │
  ▼
YandexYnisonProvider (AudioSource)
  │  track id → linked yandex_music StreamDetails
  ▼
Yandex CDN → per-track ffmpeg → session-fixed PCM
  │
  ▼
Music Assistant stream pipeline → target player
```

The provider exposes one exclusive `AudioSource` named `main` per instance.
Selecting the published device in Yandex Music triggers normal Music Assistant
`play_media` handling. Selecting the source in Music Assistant can move it to
another player when manual switching is enabled.

## Setup

1. Configure and authenticate the Yandex Music provider in Music Assistant.
2. Add **Yandex Music Connect (Ynison)**.
3. Select the Yandex Music account that owns playback.
4. Select a target player. A concrete player is required; automatic selection
   is intentionally unavailable.
5. Save the setup and select the new device in Yandex Music. The advertised
   device name follows the selected player's current name.

Reconfigure the Ynison instance to change the linked account or target player.
Rename the player in Music Assistant to change the name advertised in Yandex
Music. Legacy own-token/QR configurations are not migrated: reconfigure them
and select a Yandex Music provider.

## Runtime options

- **Allow manual player switching** — permit selecting this AudioSource on a
  player other than the configured default.
- **Stream mode** — `stable` (default) or `max_quality_dynamic`.
- **Output sample rate** — `auto`, 44100, 48000, or 96000 Hz.
- **Output bit depth** — `auto`, 16, or 24 bit.
- **Device ID** — generated once and kept as a hidden runtime value.

In auto mode, lossy audio starts at 16-bit/44.1kHz and lossless audio at
24-bit/44.1kHz when no per-track format hint is available. Before playback the
provider tries to read the real source format, so supported 96 kHz tracks can
remain 96 kHz. Auto-selected rates are then snapped to a rate supported by the
target player. Explicit sample-rate overrides are not snapped.

`max_quality_dynamic` is active only when the linked Yandex Music provider uses
**Superb** quality and both output settings are **Auto**. Otherwise the provider
continues in `stable` mode and logs one warning describing the incompatible
setting. Existing installations therefore keep their current stable behavior.

## Playback behavior

- In `stable` mode, the PCM format is frozen for the lifetime of one stream
  session.
- In `max_quality_dynamic`, each real source format is matched to the actual
  player, bridge, or group: sample rate is constrained to a supported value,
  while native bit depth is preserved in the PCM container just like MA's
  realtime AudioSource path. Tracks with the same effective PCM continue in one
  session; a changed effective PCM restarts the AudioSource on a complete
  PCM-frame boundary.
- Every track is decoded through its own ffmpeg process into that fixed format.
- Fresh `AudioFormat` objects prevent Music Assistant's ffmpeg mutations from
  leaking between stream stages.
- Progress sent to Ynison is clamped to duration because the service disconnects
  clients that report progress beyond the track end.
- User play, pause, and seek commands use strict delivery reporting; background
  progress heartbeats remain best-effort.
- Echo classification and short grace windows prevent the provider from
  interpreting its own state broadcasts as user seeks.
- RADIO queues are replenished through the linked Yandex Music provider near
  the queue tail, then the expanded queue is published back to Ynison.

A mixed-format dynamic transition can have an audible gap. Ynison's playback
clock continues while Music Assistant restarts the source, so playback resumes
from the latest reported position and may skip the time elapsed during restart.

## Connection recovery

The client performs the Ynison redirector and state-service handshakes, then
keeps the state WebSocket alive. Transient disconnects reconnect indefinitely
with saturated 5, 10, 30, and 60 second delays plus jitter. Authentication
rejections trigger an in-memory refresh from the linked account's `x_token`
when available. A short settle window after reconnect suppresses stale retained
state.

## Development

```bash
scripts/setup.sh
uv run pytest
uv run ruff check provider tests
uv run ruff format --check provider tests
uv run mypy
```

The local test dependency follows Music Assistant `dev`, while `uv.lock` pins a
tested commit and the matching models version. Use `uv sync --extra test
--frozen` to reproduce that baseline; refresh the lock intentionally when the
provider adopts a newer Music Assistant API.

## Protocol notes

Ynison uses JSON messages over WebSocket in a gRPC-like service layout. The
client first requests a redirect ticket and then opens the state-service
connection. Ynison is not a public stable API, so server-side protocol changes
can require provider updates.

## License

MIT License. See [LICENSE](LICENSE).
