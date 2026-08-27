# Required Player and Player-Derived Ynison Identity

## Provenance

- Upstream change: `music-assistant/server#6026`
- Provider pull request: `trudenboy/ma-provider-yandex-ynison#151`
- Compatible Music Assistant baseline: `5391b51f26de7316bcbc23072f5308678c59874f`
- Compatible models baseline: `music-assistant-models==1.1.204`

## Problem

Ynison allowed an automatic player sentinel and a free-form published device
name. Automatic selection could route playback to an unrelated player, while
the independent name could drift from the Music Assistant player the device
actually controlled.

## Contract

- Setup requires at least one available Music Assistant player and one enabled,
  linked Yandex Music provider instance.
- The setup form persists only the selected linked account and one concrete
  `mass_player_id`; no own-auth, QR, automatic-player, or free-form-name path is
  exposed.
- Reconfigure clears legacy authentication values instead of transferring or
  retaining a second credential owner.
- A missing or legacy automatic player fails provider load with the translated
  `no_connected_player` setup error.
- The Ynison device title follows the connected player's live display name,
  with stored player configuration and `Music Assistant` as cold-boot fallbacks.
- Player add, configuration, and provider-originated update events schedule one
  provider reload only when the effective advertised name changed.
- Target resolution never falls back to another available or playing player;
  an active explicitly selected consumer remains valid for manual switching.
- Linked-only credentials, player-owned source sessions, dynamic PCM policy,
  typed failures, and radio replenishment remain unchanged.

## Compatibility

The dependency lock advances past the merge of upstream #6026 to current
Music Assistant `dev`, including the required setup/player event APIs and
models 1.1.204.

## Verification

- Setup/config focus — 11 tests.
- Provider naming/target focus — 6 tests.
- Linked credential, authentication, dynamic-format, and provider regressions —
  249 tests.
- `uv run pytest tests/test_provider.py` — 214 tests.
- `uv run pytest` — 351 tests.
- `uv lock --check`
- `uv run ruff check provider tests`
- `uv run ruff format --check provider tests`
- `uv run mypy`
- JSON, conflict-marker, obsolete-symbol, and pre-commit gates.
