# Generation-Scoped Ynison Source Cleanup

## Provenance

- Upstream change: `music-assistant/server#5944`
- Provider pull request: `trudenboy/ma-provider-yandex-ynison#147`
- Compatible Music Assistant baseline: `c7525109a8ac73777cf34d0ffb69afe1dcd36654`
- Compatible models baseline: `music-assistant-models==1.1.198`

## Problem

Ynison cleanup is scheduled asynchronously. A delayed cleanup from an older
live-source session could therefore reach the same player after a replacement
session had started and unscoped `deselect_source(player_id)` could release the
new playback instead of the old one.

## Contract

- Cleanup captures the owning player's current audio-source session before
  clearing provider-local state.
- `deselect_source()` is scoped by owner player, this provider instance,
  source ID `main`, and the captured playback-session generation.
- A protocol bridge is never substituted for the user-facing owner.
- If no session generation is available, `None` is forwarded so the Music
  Assistant controller treats the request as a guarded no-op rather than an
  unscoped release.
- Dynamic PCM tasks and prefetched details are invalidated before cleanup, as
  required by the newer provider implementation already on `dev`.

## Compatibility

The dependency lock advances to the merge of upstream #5944, whose player
controller accepts provider/source/generation guards, with models 1.1.198.

## Verification

- Teardown focus — 5 tests, including exact generation capture, bridge owner,
  no owner, and missing generation.
- `uv run pytest tests/test_provider.py` — 212 tests.
- `uv run pytest` — 350 tests.
- `uv lock --check`
- `uv run ruff check provider tests`
- `uv run ruff format --check provider tests`
- `uv run mypy provider tests`
