# Reverse-sync: upstream PR #6887

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6887
- Provider: https://github.com/trudenboy/ma-provider-yandex-ynison/pull/188

## Contract

Upstream enabled Ruff rule S311 (non-cryptographic random generators). The provider
uses `random` only for retry and reconnect jitter, where cryptographic randomness
is not required. Both call sites carry the same `noqa: S311` justification as
upstream, so the provider stays lint-clean once the synced Ruff configuration
drops S311 from its ignore list. Runtime behavior does not change.

## Verification

- The two changed lines match the upstream diff byte-for-byte.
- `ruff check --select S311 provider/` passes with the suppressions and reports
  both call sites without them.
- Full unit suite, Ruff lint/format and mypy pass.
