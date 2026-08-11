# Issue #125 Shared HTTP Session Design

## Goal

Prevent Ynison reconnects from depending on a provider-owned default
`aiohttp.ClientSession` by routing redirector and state-service WebSockets
through Music Assistant's managed shared HTTP session. Release the fix as
4.0.3 and close GitHub issue #125 after the change is present on `origin/dev`.

## Evidence and scope

`YnisonClient` already accepts an optional `http_session`, reuses it during
reconnect, rejects a closed external session, and never closes an external
session during disconnect. The missing link is `YandexYnisonProvider`: its
`handle_async_init` constructs the client without passing `mass.http_session`,
so the client creates and owns a plain `aiohttp.ClientSession` instead.

The issue's exact ThreadedResolver explanation is not treated as proven.
Provider 3.2.2 locked aiohttp and aiodns versions that normally select an async
resolver. The accepted defect is the unnecessary private session and connector,
which bypass Music Assistant's managed resolver, DNS cache, connection pool,
and lifecycle.

## Considered approaches

1. **Inject `mass.http_session` (selected).** One provider-side argument uses an
   interface the client already supports and preserves Music Assistant's
   networking policy.
2. **Create a dedicated async-resolver session.** This duplicates connector and
   lifecycle policy and would require new ownership code.
3. **Add diagnostics only.** This could refine the field diagnosis but would not
   remove the architectural inconsistency.

No IPv4-only connector will be introduced. Music Assistant's shared connector
is dual-stack; forcing IPv4 would create an unrelated network limitation.

## Implementation

In `YandexYnisonProvider.handle_async_init`, construct `YnisonClient` with:

```python
http_session=self.mass.http_session,
```

No changes are required inside `YnisonClient`. Authentication and Ynison
protocol headers remain request-local, and existing external-session ownership
guards remain authoritative.

## Tests

Add one provider-level regression test around `handle_async_init` that keeps a
real `YnisonClient`, forbids construction of a private `ClientSession`, and
drives `connect()` up to a controlled redirector failure. The test must fail
before the production change and pass after it.

Retain the existing client-level tests that prove reconnect reuses an external
session and disconnect does not close it. Run the complete pytest suite, mypy,
Ruff, method-order, lock validation, codespell, pre-commit, and Astro build.

## Release and GitHub workflow

- Bump `VERSION` from 4.0.2 to 4.0.3.
- Add a 4.0.3 changelog entry describing shared-session reconnect hardening and
  crediting issue #125 without endorsing the unproven resolver diagnosis.
- Merge the verified feature branch into `dev`.
- Push `dev` to `origin`.
- Close issue #125 only after the push succeeds, with the exact concise comment
  `Fixed in 4.0.3.`

No release tag or GitHub Release is part of this task.
