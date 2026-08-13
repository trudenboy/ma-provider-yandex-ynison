# Narrow Provider Error Handling Design

## Context

Music Assistant server PR #5589 received two open review comments. One asks
Ynison to use `ya_passport_auth.ma.BorrowedCredentialSource`; the other asks
the provider to replace broad `except Exception` catches and generic
`RuntimeError` exceptions with narrower or Music Assistant-specific errors.

The target authentication architecture is moving away from the
Music Assistant-specific credential-source API in `ya-passport-auth`.
Consequently, this change must not adopt `BorrowedCredentialSource` or alter
the library dependency. The provider-local adapter is intentional because it
reads credentials from Music Assistant setup data through
`Provider.get_setup_value`, while Yandex Music remains their only persistent
owner.

## Scope

This work changes only `trudenboy/ma-provider-yandex-ynison` and produces one
draft PR against `dev`.

In scope:

- Clarify the narrow role and architectural ownership of the local linked
  credential adapter.
- Replace generic provider-facing exceptions with Music Assistant error types.
- Narrow broad exception catches in `provider/provider.py` wherever the called
  contract identifies expected failures.
- Preserve best-effort behavior for player cleanup, prefetch, capability
  inspection, and radio replenishment without masking programmer errors.
- Add focused regression tests and a changelog entry.

Out of scope:

- Changes or a PR in `ya-passport-auth`.
- Adopting or modifying `BorrowedCredentialSource`.
- Changes to `provider/ynison_client.py`, whose transport and callback
  boundaries require a separate lifecycle analysis.
- Updating `VERSION`, merging PRs, releasing packages, or writing replies on
  upstream GitHub.

## Architecture

### Linked credentials

`YandexMusicCredentialSource` remains provider-local and private to the
Ynison integration. It performs only host-specific work:

1. Resolve the configured Yandex Music provider instance from Music
   Assistant.
2. Validate that the instance is a loaded music provider with the
   `yandex_music` domain.
3. Read the setup-owned `token` and `x_token` values through the owner's
   public `get_setup_value` method.
4. Normalize non-empty values to `SecretStr` without persisting or rotating
   credentials.

Ynison continues to own its temporary music-token cache and refresh
coordination because those operations are part of its connection lifecycle.
No dependency on the deprecated credential-source abstraction is introduced.

### Error taxonomy

Provider methods expose Music Assistant errors when a failure crosses a
framework boundary:

- A forbidden source/player switch raises `ActionUnavailable`.
- Exhausted stream-detail retries raise `RetriesExhausted`.
- Temporary upstream failures eligible for retry are
  `ResourceTemporarilyUnavailable` and `RateLimited`.
- Player stop failures are handled as `PlayerCommandFailed`; unexpected
  exceptions raised by Music Assistant player commands are already wrapped by
  the player controller.
- Other known Music Assistant failures use `MusicAssistantError` only at
  best-effort boundaries where falling back or ending the current stream is
  deliberate.

Permanent errors such as authentication failure and missing media are not
retried. Unexpected Python exceptions are allowed to propagate rather than
being silently converted into retries or fallbacks.

Capability parsing is not a Music Assistant service failure. Its defensive
fallback catches only structural/value failures expected from malformed or
partially initialized player capability data: `AttributeError`, `TypeError`,
and `ValueError`.

### Retry and fallback behavior

The existing retry count and backoff timings remain unchanged. Only transient
MA errors enter retry loops. When all attempts fail, the raised
`RetriesExhausted` retains the last transient error as its cause.

Best-effort paths preserve their current user-visible behavior:

- failure to stop a superseded player is logged and selection continues;
- ordinary prefetch failure keeps the current PCM format;
- inability to inspect player capabilities uses the source PCM signature;
- radio replenishment failure leaves the current queue unchanged.

Cancellation always propagates. Programmer errors and contract violations no
longer disappear behind a fallback.

## Testing

Tests follow red/green/refactor TDD and cover:

- the two generic exceptions becoming the intended MA error types;
- transient stream-detail failures retrying and ending as
  `RetriesExhausted`;
- permanent MA errors bypassing retries;
- dynamic prefetch retrying transient errors while propagating permanent or
  unexpected errors;
- expected player-command, prefetch, capability, and radio failures retaining
  their documented fallback behavior;
- unexpected exceptions escaping best-effort blocks that no longer own them;
- linked credentials continuing to come exclusively from setup data.

After focused tests pass, the complete provider test, lint, formatting,
typing, pre-commit, and whitespace checks run before publication.

## Delivery

The completed change is committed on `fix/narrow-provider-errors`, pushed to
`origin`, and opened as a draft PR targeting `dev`. The PR body explains both
review findings, the deliberate provider-local credential boundary, the new
error taxonomy, and verification results. It does not modify or reply to
music-assistant/server PR #5589.
