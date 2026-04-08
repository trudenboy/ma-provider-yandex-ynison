# CLAUDE.md — Yandex Ynison Plugin

## Project overview

Music Assistant plugin that makes MA players appear as devices in the Yandex Music app via the Ynison protocol (Yandex's equivalent of Spotify Connect).

- **Type**: `PluginProvider` with `ProviderFeature.AUDIO_SOURCE`
- **Manifest type**: `plugin`
- **Domain**: `yandex_ynison`
- **Architecture reference**: `spotify_connect` provider in MA server

## Architecture

```
Yandex Music app (phone/web)
  -> Ynison WebSocket <-> YandexYnisonProvider
    -> receives track_id from PlayerState
    -> fetches audio via Yandex Music API (reuses yandex-music provider if available)
    -> PCM audio -> PluginSource -> MA Player (Chromecast/DLNA/etc)
    <- on_play/pause/seek -> update_playing_status back to Ynison
```

## Key modules

| File | Purpose |
|------|---------|
| `provider/__init__.py` | Setup function, config entries, `SUPPORTED_FEATURES` |
| `provider/provider.py` | `YandexYnisonProvider(PluginProvider)` — main plugin class |
| `provider/ynison_client.py` | `YnisonClient` — WebSocket client for the Ynison protocol |
| `provider/constants.py` | URLs, config keys, defaults |
| `provider/manifest.json` | Plugin metadata |

## Development setup

```bash
cd /Users/renso/Projects/ma-provider-yandex-ynison
scripts/setup.sh       # or: uv sync --extra test
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy            # type check
```

## CI infrastructure

Uses reusable workflows from `trudenboy/ma-provider-tools`:
- `reusable-test.yml` — pytest, ruff, mypy, codespell
- `reusable-release.yml` — tag-based releases
- `reusable-security.yml` — dependency audit
- `reusable-sync-to-fork.yml` — fork sync for MA server integration

## Ynison protocol notes

- Transport: gRPC-over-WebSocket, JSON messages (not binary protobuf)
- Two-step connection: Redirector -> State Service
- Redirect URL: `wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison`
- State URL: `wss://{host}/ynison_state.YnisonStateService/PutYnisonState`
- Auth: `Authorization: OAuth {token}`, device info in `Sec-WebSocket-Protocol` header
- Reference implementations: `bulatorr/go-yaynison` (Go), `FozerG/YandexMusicRPC` (Python)
