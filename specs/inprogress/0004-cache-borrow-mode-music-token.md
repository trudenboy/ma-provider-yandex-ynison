---
id: "0004"
title: "Cache in-memory music token to avoid Passport hammering"
size: M
status: inprogress
priority: P2
effort_minutes: 25
---

## Problem Statement

Two paths in the plugin call `refresh_music_token(x_token)` directly on every invocation, with no caching:

- `_resolve_token` — runs on `handle_async_init`. In borrow mode with x_token-only YM (no music token cached upstream), this fires on every plugin load.
- `_refresh_ynison_token` — runs on every Ynison WS 401/403. In an auth-failure storm (token expired during a network blip, reconnect loop), this fires repeatedly until the WS re-establishes.

Each call hits Yandex Passport's `/refresh` endpoint. The library already bounds each call at 30 s (per spec 0003 verification), but Passport rate-limits per (client_id, account); back-to-back refreshes during a reconnect storm risk tripping captcha or hard rate-limits, which then degrades the linked `yandex_music` provider too.

## Solution Summary

Introduce an in-memory cache keyed on a SHA-256 hash of `x_token`. Cache hits within a 50-minute TTL (music tokens live ~60 min on Yandex's side; 10-min headroom) return the previously-refreshed `SecretStr` without a network call. The `_refresh_ynison_token` path (which by contract is reached only on 401) bypasses and invalidates the cache before refreshing, so a server-rejected token is never re-served. A 4-entry LRU cap bounds memory growth across x_token rotations. An `asyncio.Lock` ensures concurrent reconnect attempts coalesce into one refresh.

## Acceptance Criteria

1. New private method `async def _refresh_via_x_token(self, x_token: str) -> SecretStr` on `YandexYnisonProvider` performs cache-or-refresh.
2. Cache TTL is `_MUSIC_TOKEN_TTL_S = 50 * 60` (declared next to other module-level constants).
3. Cache key uses `hashlib.sha256(x_token.encode()).hexdigest()` — the raw x_token is never stored in dict keys.
4. Cache enforces a 4-entry LRU bound; oldest entry is evicted when a 5th distinct x_token is added.
5. `_resolve_token` calls `_refresh_via_x_token` for both borrow-with-x_token and own-with-x_token branches (replaces the two existing `refresh_music_token(SecretStr(x_token))` direct calls).
6. `_refresh_ynison_token` calls `_refresh_via_x_token` AND pops the cache entry for the current x_token *first* (the 401 means the cached token is provably stale).
7. Concurrent `_resolve_token` calls from the same x_token coalesce — only one `refresh_music_token` await runs (verified by `asyncio.gather` + slow mocked refresh).
8. A `_now` callable seam allows tests to advance time without `monkeypatch.setattr(time, "monotonic", ...)`.
9. No raw x_token, no music token, no cache hash appears in any log line or exception message.
10. All existing tests remain green; new `TestMusicTokenCache` class adds ≥5 new tests.

## Test Plan

- `test_resolve_token_caches_x_token_refresh` — first call hits `refresh_music_token`, second within TTL is a cache hit.
- `test_resolve_token_refreshes_after_ttl_expires` — `_now` advances past TTL; the second call refreshes.
- `test_refresh_ynison_token_invalidates_cache` — pre-seed cache, call `_refresh_ynison_token`, assert `refresh_music_token` IS called (cache bypassed) and the cache no longer contains the old entry.
- `test_concurrent_resolve_token_calls_refresh_once` — `asyncio.gather` of two `_resolve_token` calls; with a slow mocked refresh, `await_count == 1`.
- `test_cache_lru_evicts_oldest_after_four_x_tokens` — populate 4 entries, add a 5th; the first is gone.
- `test_cache_does_not_log_token_or_hash` — `caplog` at DEBUG; assert no record `.message` / `.args` contains the x_token, the music token, or the SHA-256 hex digest. Negative test for credential hygiene.

### Sequence diagram (borrow-mode reconnect storm)

```
ws_connect → 401
   │
   ▼
on_auth_failure ──► _refresh_ynison_token
                        │
                        ├── pop(cache_key)   (invalidate stale)
                        │
                        ▼
                        _refresh_via_x_token
                        ├── cache miss → lock → refresh_music_token → store → return
                        │
                        └── concurrent same x_token → lock waits → reads stored → return

ws_connect → 401 again (fresh token but server still 401s)
   │
   ▼
on_auth_failure ──► _refresh_ynison_token
                        │
                        └── pop again, refresh again (one refresh per 401, not per attempt)
```

### Data model

```python
@dataclass(frozen=True)
class _CachedToken:
    token: SecretStr
    expires_monotonic: float

# Owned by YandexYnisonProvider:
self._token_cache: dict[str, _CachedToken] = {}            # SHA-256 hex → CachedToken
self._token_refresh_lock: asyncio.Lock = asyncio.Lock()    # one refresh at a time
self._now: Callable[[], float] = time.monotonic            # test seam
```
