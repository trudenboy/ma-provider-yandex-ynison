# Ynison Live Research Implementation Plan

Date: 2026-09-01
Target release: 4.3.0 (stable)
Source research: `docs/research/2026-09-01-live-ynison-official-client.md`

## Scope

Implement the protocol behavior confirmed by live testing:

- clear stale ownership on the server disconnect sentinel;
- classify empty-version status heartbeats by recent outbound causality;
- preserve authoritative phone seeks and transfers across heartbeat/reconnect races;
- follow `shuffle_optional.playable_indices` consistently;
- implement repeat NONE, ONE, and ALL at natural completion;
- expose repeat and shuffle through Music Assistant AudioSource controls;
- add tested low-level Ynison add-next, add-last, remove, and move operations;
- refresh credentials once when an invalid token produces an empty redirect;
- investigate passive recovery and server-directed backoff before implementing them;
- complete automated and live validation before releasing 4.3.0.

## Delivery Sequence

1. Align `ya-passport-auth` in package metadata, runtime manifest, and lockfile.
2. Add sanitized live-protocol fixtures.
3. Fix disconnect ownership parsing.
4. Add bounded outbound status watermarks and authoritative-event barriers.
5. Introduce one queue-order model used by state, metadata, streaming, navigation,
   prefetch, repeat, shuffle, and queue edits.
6. Separate natural completion from explicit next and implement repeat modes.
7. Advertise and dispatch Music Assistant repeat/shuffle controls.
8. Add low-level queue-edit client operations only; do not invent a provider-specific
   Music Assistant API for operations the AudioSource contract does not expose.
9. Add bounded empty-redirect authentication recovery.
10. Run passive-recovery and server-backoff discovery matrices. Implement only wire
    behavior supported by new evidence.
11. Run all automated gates, self-review, and the complete live regression matrix.
12. Add the 4.3.0 changelog block. The maintainer updates `VERSION` and approves the
    release; the pipeline publishes and synchronizes the stable provider.

## TDD Seams

- `YnisonClient`: message construction, parsing, echo classification, reconnect,
  authentication, and queue-edit sends.
- Queue model: pure validation, logical order, navigation, repeat, shuffle, and edit
  reconciliation.
- `YandexYnisonProvider.on_source_control` and `AudioSource`: externally observable
  repeat/shuffle behavior and capabilities.
- Live matrix: official Android client, a real Yandex Station, and the Music
  Assistant Ynison device.

Every behavior change follows red, green, then review/refactor. Fixtures use aliases
only and contain no account, credential, ticket, session, queue, track, or device
identifiers from the live account.

## Discovery Gates

### Shuffle and edits

Before relying on a position interpretation, capture a known alias queue and verify
whether `current_playable_index` and `playable_indices` use original or logical
positions. Capture enable, disable, next, previous, add-next, add-last, remove, and
move, including operations around the current item.

### Passive recovery

Do not treat session-parameter changes, empty EOV sync, or an ownership claim as a
recovery: live testing disproved those approaches. A solution must obtain an
authoritative current queue and status before activating Music Assistant. Five
consecutive MA-to-Station-to-MA cycles must pass before release.

### Server backoff

Do not guess header precedence or the `Ynison-Backoff-Millis` value format. Capture a
real header or error detail first. Without evidence, retain bounded local exponential
backoff and defer server-directive parsing.

## Automated Gate

```bash
uv lock --check
uv sync --extra test --frozen
uv run pytest
uv run ruff check provider tests
uv run ruff format --check provider tests
uv run mypy
pre-commit run --all-files
```

Required invariants:

- metadata track, streamed track, and current Ynison playable are identical;
- a valid logical order contains each playable exactly once;
- a pure shuffle toggle preserves the current playable;
- progress never exceeds duration;
- failed strict sends do not commit local queue or heartbeat state;
- authoritative phone states are never hidden by a local watermark;
- repeat ONE restarts without waiting for a track-ID change;
- repeat NONE reaches terminal state without a 30-second wait.

## Live Gate

Exercise transfer, play, pause, seek, next, previous, natural completion, RADIO
replenishment, heartbeat/seek races, all repeat modes, shuffle, all queue edits,
controlled close, invalid JSON, physical network loss, invalid-token refresh, and
five passive transfer cycles. Publish only sanitized evidence.

Release is blocked by any duplicate playback, stale queue rollback, reconnect storm,
repeat/shuffle mismatch, metadata/audio mismatch, credential disclosure, failed
automated gate, or unreliable passive transfer.

## Implementation Status

As of 2026-09-01, the dependency baseline, sanitized fixtures, disconnect-sentinel
handling, heartbeat watermarking, queue-order model, repeat/shuffle AudioSource
controls, queue-edit client methods, bounded empty-redirect refresh, and associated
automated tests are implemented. The complete repository gate passes with 380 tests,
Ruff, formatting, mypy, and pre-commit.

The passive recovery discovery gate is complete. An earlier apparent failure was an
invalid UI experiment: screenshot coordinates were used directly against a larger
ADB input surface, so the Music Assistant row had not actually been selected. With
UIAutomator bounds, five consecutive Music Assistant-to-Station-to-Music-Assistant
cycles succeeded. Every transfer away emitted the disconnect sentinel and cleared
ownership; every transfer back emitted an authoritative phone-authored queue/status
with current progress.

Live testing also confirmed that `current_playable_index` is an original-list index
and `shuffle_optional.playable_indices` is the logical order of those indices. Repeat
ONE restarted the same index and track at zero. That test exposed a duplicate
completion race because Ynison attaches a complete unchanged queue to some heartbeat
echoes. Echo classification now accepts a matching status when that attached queue is
unchanged; the repeated live test produced one completion followed by monotonically
increasing progress from zero.

Server-directed backoff parsing remains deferred because no live backoff/go-away
header was observed. The bounded local exponential fallback remains in place.

## Release

The contributor PR targets `dev`, includes completed specs and one canonical 4.3.0
changelog block, and does not modify `VERSION`. After explicit approval, the
maintainer sets root `VERSION` to `4.3.0`. The pipeline must create `v4.3.0`, publish
the stable GitHub Release, and synchronize `integration/dev` and
`upstream/yandex_ynison`. Regressions after publication are fixed forward in 4.3.1.
