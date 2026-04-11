# Copilot Instructions — Yandex Ynison Plugin

## Project overview

Music Assistant plugin that makes MA players appear as devices in the Yandex Music app via the Ynison protocol (Yandex's equivalent of Spotify Connect). Follows the `spotify_connect` provider pattern from the MA server.

- **Type**: `PluginProvider` with `ProviderFeature.AUDIO_SOURCE`
- **Manifest type**: `plugin`, **domain**: `yandex_ynison`
- **Status**: Alpha — under active development

## Architecture

```
Yandex Music app (phone/web)
  → Ynison WebSocket ↔ YandexYnisonProvider
    → receives track_id from PlayerState
    → fetches audio via Yandex Music API (reuses yandex-music provider if available)
    → PCM audio → PluginSource → MA Player (Chromecast/DLNA/etc)
    ← play/pause/seek → update_playing_status back to Ynison
```

Key data flow: `YnisonClient` maintains a persistent WebSocket to the Ynison state service. When the active track changes, it fires `on_state_update` → `YandexYnisonProvider._handle_ynison_state` resolves the track via the Yandex Music API, pipes audio through ffmpeg into PCM, and feeds it to MA's player infrastructure via `PluginSource`.

### Ynison protocol

- Transport: gRPC-over-WebSocket with JSON messages (not binary protobuf)
- Two-step connection: Redirector → State Service
- Auth: `Authorization: OAuth {token}` + device info in `Sec-WebSocket-Protocol` header
- Reference implementations: `bulatorr/go-yaynison` (Go), `FozerG/YandexMusicRPC` (Python)

## Commands

```bash
# Setup
scripts/setup.sh          # or: uv sync --extra test

# Test
uv run pytest                              # full suite
uv run pytest tests/test_ynison_client.py  # single file
uv run pytest -k "test_parse_state"        # single test by name

# Lint & format
uv run ruff check .       # lint (auto-fix enabled in config)
uv run ruff format .      # format

# Type check
uv run mypy               # strict mode, packages: provider, tests
```

## Key conventions

- **Python 3.12+** required. All modules use `from __future__ import annotations`.
- **`uv`** is the package manager (not pip). Dependencies and test extras are in `pyproject.toml`.
- **Ruff** is configured with `select = ["ALL"]` and a large ignore list — check `ruff.toml` before adding new rules.
- **mypy** runs in strict mode with `disallow_untyped_defs = true`. All function signatures need type annotations.
- **pytest-asyncio** with `asyncio_mode = "auto"` — async test functions are auto-detected, no `@pytest.mark.asyncio` needed.
- **Line length**: 100 characters (enforced by ruff).
- **Docstrings**: PEP 257 convention. Every module and public class needs a docstring.
- **Constants**: All config keys and protocol values live in `provider/constants.py` using `typing.Final`.
- **Imports**: `music_assistant` is listed as first-party in isort config. Use `TYPE_CHECKING` guard for type-only imports from MA.
- **Test mocks**: Tests mock the MA `MusicAssistant` instance and `ProviderConfig` — see `_make_mock_mass()` and `_make_mock_config()` helpers in `tests/test_provider.py`.
- **CI**: Uses reusable workflows from `trudenboy/ma-provider-tools` — do not add CI config directly; modify the reusable workflows repo instead.
- **Pre-commit**: Configured with ruff, mypy, codespell, and structural checks. Run `uv run pre-commit run --all-files` to check locally.
