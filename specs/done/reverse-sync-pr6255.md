# Reverse-sync: upstream PR #6255

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6255
- Provider: https://github.com/trudenboy/ma-provider-yandex-ynison/pull/165
- Shared compatibility baseline: provider PR #172.

## Contract

Internal credential-owner discovery uses Music Assistant's providers collection
instead of its user-filtered API method. Match only the configured Yandex Music
instance, preserving account isolation, startup retry, and wrong-type rejection.
This port does not add household configuration or restore own credentials.

## Conflict resolution and verification

Preserve the local removal of legacy own-mode and display-name tests. Adapt the
existing matching tests to the providers collection; they call the real matching
method and cover missing, incompatible, unavailable, and exact-instance owners.
