# Yandex Music Connect (Ynison) — Music Assistant Plugin

Makes any Music Assistant player appear as a playback device in the official Yandex Music app via the Ynison protocol.

## How it works

1. Plugin connects to Yandex's Ynison service (WebSocket)
2. Your MA player appears as a device in the Yandex Music app
3. Select the device in Yandex Music -> audio streams through MA to your speaker
4. Control playback from the Yandex Music app (play/pause/skip/volume)

## Status

**Alpha** — under active development. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.

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
