# Player-Owned Ynison Audio Source Sessions

## Provenance

- Upstream change: `music-assistant/server#5914`
- Provider pull request: `trudenboy/ma-provider-yandex-ynison#143`
- Compatible Music Assistant baseline: `21fcc2c56e024c440964f12516a53686c78c2c29`
- Compatible models baseline: `music-assistant-models==1.1.195`

## Problem

Music Assistant moved live audio sources out of queues and onto player-owned
sessions so starting an external source no longer replaces the user's queue.
Ynison previously treated the callback's third argument as a queue ID and used
it interchangeably with the physical player consuming the PCM stream. Those
IDs differ when a protocol bridge or group member renders the source.

## Contract

- `_in_use_by_player` identifies the user-facing player that owns the live
  source session.
- `_active_player_id` identifies the physical player or protocol bridge that
  consumes Ynison PCM.
- `on_source_selected()` records both identities and the playback-session
  token; a bridge and its owner never stop each other during selection.
- `on_source_unselected()` rejects stale session tokens before releasing the
  player-owned claim.
- Capability changes refresh the source object held by the owning player's
  live session.
- Clearing playback deselects the source from its owner, while transport and
  progress updates continue to target the physical consumer.
- Dynamic PCM launch and restart paths retain the owner identity, preserve the
  active generation, and continue to use the live-source forwarding entrypoint.
- Operational `PlayerCommandFailed` errors remain recoverable; unexpected
  controller errors still propagate.

## Compatibility

The dependency lock advances to the merge of upstream #5914, which supplies
the player-owned plugin callbacks and `PlayerController.refresh_source`, with
models 1.1.195.

## Verification

- Lifecycle focus: selection, bridge ownership, release, stale callbacks,
  capability refresh, pause, and slot release — 22 tests.
- Dynamic PCM focus — 30 tests.
- Aggregate pre-release review — 3 bridge/owner regressions covering locked
  switching, dynamic restart ownership, and physical-consumer progress refresh.
- `uv run pytest tests/test_provider.py` — 211 tests.
- `uv run pytest` — 349 tests.
- `uv lock --check`
- `uv run ruff check provider tests`
- `uv run ruff format --check provider tests`
- `uv run mypy provider tests`
