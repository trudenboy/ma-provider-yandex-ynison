# Reverse-sync: upstream PR #6914

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6914
- Ported manually ahead of the reverse-sync radar to unblock
  music-assistant/server#5589, which conflicted with this upstream change.

## Contract

Upstream enabled Ruff rule TRY301 (`raise` inside `try`) and suppressed it where
the raised exception is intentionally handled by the enclosing `try`. The provider
has two such sites:

- the stream-details owner check, whose `_StreamOwnerMismatchError` is re-raised
  unchanged by the dedicated `except` below; this matches the upstream suppression
  and its justification text;
- the reconnect loop's closed external-session guard. Upstream raises
  `RuntimeError` there; the provider raises `ResourceTemporarilyUnavailable`,
  which the loop's transient-failure `except` handles. It carries the same
  justification as upstream.

Runtime behavior does not change.

## Verification

- With the synced Ruff configuration that enables TRY301, `ruff check` reports
  both sites without the suppressions and passes with them.
- Full unit suite, Ruff format and mypy pass.
