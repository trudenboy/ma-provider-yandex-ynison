# Reverse-sync: upstream PR #6526

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6526
- Provider: https://github.com/trudenboy/ma-provider-yandex-ynison/pull/171
- Shared compatibility baseline: provider PR #172.

## Contract

Radio prefetch tasks have the name ynison_prefetch followed by the provider's
instance ID. The name identifies the source in Music Assistant task diagnostics
and does not change queue replenishment, lifecycle, or authentication.

## Verification

The radio prefetch test uses MusicAssistant.create_task itself and inspects the
resulting asyncio task name, then awaits it and checks the expanded queue. Removing
the provider's task_name argument makes this regression fail. The former lambda
discarded keyword arguments, so it could not test this upstream contract.
