# Linked Yandex Music Stream Capacity

## Provenance

- Upstream change: `music-assistant/server#5773`
- Provider pull request: `trudenboy/ma-provider-yandex-ynison#138`
- Compatible Music Assistant baseline: `f84a9dbc3ae1f622e8beedd21984df8a37d3f9c1`
- Compatible models baseline: `music-assistant-models==1.1.194`

## Problem

Ynison resolves and reads audio through one configured Yandex Music provider
instance. Streaming outside that instance's shared capacity guard could exceed
the account's concurrent-stream limit. Reusing cached details after the linked
instance changed could also charge or stream from the wrong account.

## Contract

- Each track captures the exact linked Yandex Music provider instance before
  resolving stream details.
- Stream-detail cache keys include that provider instance ID, and cached or
  freshly resolved details owned by another instance are rejected.
- The linked provider's shared stream slot is held only while the raw source is
  consumed, including the ffmpeg decode that reads it.
- Closing the outer Ynison stream, changing tracks, or switching linked
  providers finalizes the nested generators and releases the slot immediately.
- A linked-provider capacity timeout remains a typed
  `ProviderStreamLimitError`; deterministic owner mismatches are not retried.
- Existing retry/backoff remains limited to
  `ResourceTemporarilyUnavailable`.

## Compatibility

The provider protocol retains the Yandex-specific quality accessor and adds
only the shared Music Assistant fields needed for capacity accounting:
`instance_id`, `available`, and `acquire_stream_slot()`.

## Verification

- Imported upstream regressions cover slot acquisition, typed capacity errors,
  instance switches, provider-specific cache keys, mismatched owners, consumer
  cancellation, and track-change release ordering.
- Existing error-boundary tests still prove that operational Music Assistant
  failures end the track while unexpected internal exceptions propagate.
- `uv run pytest tests/test_provider.py` — 208 tests
- `uv run pytest` — 346 tests on the pinned Music Assistant baseline
- `uv run ruff check provider tests`
- `uv run ruff format --check provider tests`
- `uv run mypy provider tests`
