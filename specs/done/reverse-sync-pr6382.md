# Reverse-sync: upstream PR #6382

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6382
- Provider: https://github.com/trudenboy/ma-provider-yandex-ynison/pull/167
- Shared compatibility baseline: provider PR #172.

## Contract

When finish raises SetupFlowError, show the form again with the original error
object. Preserve its translation key, arguments and owner, and retain the linked
account and concrete player selection. Keep legacy-auth cleanup on reconfigure.
Do not restore obsolete QR login or independent credentials.

## Verification

A regression calls run_setup, fails on its former conversion to a string, and
passes when the original error reaches the retry form. Existing retry coverage
now checks the typed error and its translation key because the upstream form
contract explicitly supports SetupFlowError. All setup-flow tests pass.
