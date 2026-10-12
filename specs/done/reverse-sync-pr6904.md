# Reverse-sync: upstream PR #6904

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6904
- Provider: https://github.com/trudenboy/ma-provider-yandex-ynison/pull/193

## Contract

Upstream enabled Ruff rule S105 (hardcoded passwords) and suppressed it on the
Ynison constants that name credential config keys. Those values are setting keys,
not secrets. The provider keeps only the linked-account keys
`YANDEX_MUSIC_CONF_TOKEN` and `YANDEX_MUSIC_CONF_X_TOKEN`; both carry the same
`noqa: S105 - config key` justification as upstream. The upstream own-mode
constants (`CONF_TOKEN`, `CONF_X_TOKEN`, `CONF_ACCOUNT_LOGIN`,
`CONF_REMEMBER_SESSION`) were removed from the provider by spec
`0007-linked-yandex-auth-only` and are not restored. Runtime behavior does not
change.

## Verification

- The snapshot-merge conflict was resolved to the provider's constants plus the
  two upstream suppressions; the suppression text matches upstream.
- With the synced Ruff configuration that enables S105, `ruff check` reports both
  constants without the suppressions and passes with them.
