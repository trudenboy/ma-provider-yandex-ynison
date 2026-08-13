# Narrow Provider Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ynison expose Music Assistant error types and retry or suppress only failures its contracts classify as expected, while preserving its provider-local setup-data credential boundary.

**Architecture:** `provider/provider.py` remains the coordinator, but its framework boundaries use `music_assistant_models.errors` instead of generic runtime errors. Retry loops accept transient MA failures only; best-effort paths accept typed MA failures or narrowly defined capability-data errors. `provider/credential_source.py` remains local and documents why it must not adopt `ya_passport_auth.ma.BorrowedCredentialSource`.

**Tech Stack:** Python 3.14, asyncio, Music Assistant models, pytest/pytest-asyncio, Ruff, mypy, pre-commit, uv.

## Global Constraints

- Change only `trudenboy/ma-provider-yandex-ynison`.
- Do not modify `ya-passport-auth`, `provider/ynison_client.py`, `VERSION`, or upstream PR #5589.
- Do not import or adopt `ya_passport_auth.ma.BorrowedCredentialSource`.
- Preserve Yandex Music as the only persistent credential owner and read its credentials through `Provider.get_setup_value`.
- Preserve the existing retry counts, backoff timings, and user-visible fallback behavior.
- Unexpected Python exceptions must propagate instead of being retried or suppressed.
- Publish one draft PR from `fix/narrow-provider-errors` to `dev`; do not merge it.

---

### Task 1: Define framework-facing error types

**Files:**
- Modify: `tests/test_provider.py`
- Modify: `provider/provider.py`

**Interfaces:**
- Consumes: `ActionUnavailable` and `RetriesExhausted` from `music_assistant_models.errors`.
- Produces: `on_source_selected(...)` raises `ActionUnavailable`; `_get_stream_details_with_retry(...)` retries `ResourceTemporarilyUnavailable` and raises `RetriesExhausted` when its retry budget is exhausted.

- [ ] **Step 1: Write failing tests for source selection and stream-detail retry taxonomy**

Update the error imports and assertions in `tests/test_provider.py`:

```python
from music_assistant_models.errors import (
    ActionUnavailable,
    LoginFailed,
    MediaNotFoundError,
    PlayerCommandFailed,
    ResourceTemporarilyUnavailable,
    RetriesExhausted,
    UnsupportedFeaturedException,
)

with pytest.raises(ActionUnavailable, match="Player switching is disabled"):
    await provider.on_source_selected(...)
```

Change the retry fixtures from `RuntimeError` to
`ResourceTemporarilyUnavailable`, assert `RetriesExhausted` after
`_API_MAX_RETRIES`, and add a permanent-failure test:

```python
async def test_permanent_error_is_not_retried(self) -> None:
    provider = _make_provider()
    mock_yp = MagicMock()
    mock_yp.get_stream_details = AsyncMock(side_effect=MediaNotFoundError("missing"))
    provider._yandex_provider = mock_yp

    with pytest.raises(MediaNotFoundError, match="missing"):
        await provider._get_stream_details_with_retry("t1")

    mock_yp.get_stream_details.assert_awaited_once()
```

- [ ] **Step 2: Run the focused tests and verify red**

Run:

```bash
uv run pytest -q tests/test_provider.py::TestSourceSelection tests/test_provider.py::TestGetStreamDetailsWithRetry
```

Expected: failures show `RuntimeError` instead of `ActionUnavailable`, raw transient errors instead of `RetriesExhausted`, and unwanted retries for `MediaNotFoundError`.

- [ ] **Step 3: Implement typed public errors and transient-only retries**

Import these types in `provider/provider.py`:

```python
from music_assistant_models.errors import (
    ActionUnavailable,
    LoginFailed,
    MediaNotFoundError,
    MusicAssistantError,
    PlayerCommandFailed,
    ResourceTemporarilyUnavailable,
    RetriesExhausted,
    UnsupportedFeaturedException,
)
```

Raise `ActionUnavailable` in `on_source_selected`. In
`_get_stream_details_with_retry`, retain explicit cancellation propagation,
catch only `ResourceTemporarilyUnavailable`, and finish with:

```python
msg = f"get_stream_details failed after {_API_MAX_RETRIES} attempts for {track_id}"
raise RetriesExhausted(msg) from last_err
```

- [ ] **Step 4: Run focused tests and verify green**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add provider/provider.py tests/test_provider.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "fix: use typed errors for stream coordination"
```

---

### Task 2: Narrow best-effort player and stream catches

**Files:**
- Modify: `tests/test_provider.py`
- Modify: `provider/provider.py`

**Interfaces:**
- Consumes: `PlayerCommandFailed`, `MusicAssistantError`, and `RetriesExhausted` introduced or imported in Task 1.
- Produces: known player/MA failures retain current fallback behavior; unrelated `RuntimeError` instances propagate.

- [ ] **Step 1: Write failing fallback-boundary tests**

Change the existing pause failure fixture to
`PlayerCommandFailed("boom")`. Add paired tests showing unexpected exceptions
are not hidden:

```python
async def test_unexpected_cmd_stop_error_propagates(self) -> None:
    provider = _make_provider()
    provider._active_player_id = "spb_bridge1"
    provider._in_use_by_queue = "player1"
    provider.mass.players.cmd_stop = AsyncMock(side_effect=RuntimeError("bug"))

    with pytest.raises(RuntimeError, match="bug"):
        await provider._pause_playback()
```

Add equivalent coverage for stopping a superseded player in
`TestSourceSelection`. Add a `TestStreamTrackErrorHandling` class proving a
`RetriesExhausted` from stream-detail lookup ends the generator while a raw
`RuntimeError` propagates from `anext(...)`.

- [ ] **Step 2: Run the focused tests and verify red**

Run:

```bash
uv run pytest -q tests/test_provider.py::TestSourceSelection tests/test_provider.py::TestPausePlayback tests/test_provider.py::TestStreamTrackErrorHandling
```

Expected: raw `RuntimeError` is currently swallowed by the broad catches.

- [ ] **Step 3: Narrow the catches**

Apply these replacements in `provider/provider.py`:

```python
try:
    await self.mass.players.cmd_stop(prev_player_id)
except PlayerCommandFailed as err:
    ...

try:
    stream_details = await self._get_stream_details_with_retry(track_id)
except MusicAssistantError:
    ...

try:
    await self.mass.players.cmd_stop(target)
except PlayerCommandFailed:
    ...
```

Do not add an `Exception` fallback.

- [ ] **Step 4: Run focused tests and verify green**

Run the command from Step 2. Expected: selected tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add provider/provider.py tests/test_provider.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "fix: narrow player and stream failure boundaries"
```

---

### Task 3: Narrow prefetch, capability, and radio fallbacks

**Files:**
- Modify: `tests/test_provider.py`
- Modify: `provider/provider.py`

**Interfaces:**
- Consumes: typed MA errors from Task 1 and `select_effective_pcm(...)` raising `ValueError` for invalid source metadata.
- Produces: `_prefetch_format_for_track` and `_replenish_radio_queue` suppress `MusicAssistantError`; capability helpers suppress only `AttributeError`, `TypeError`, and `ValueError`; `_get_dynamic_stream_details` retries transient exhaustion and invalid source metadata only.

- [ ] **Step 1: Write failing tests for each fallback contract**

Add tests that exercise real methods with minimal stubs:

```python
async def test_prefetch_known_ma_error_keeps_format(self) -> None:
    provider = _make_provider()
    before = dict(provider._normalized_params)
    _stub_attr(
        provider,
        "_get_stream_details_with_retry",
        AsyncMock(side_effect=MediaNotFoundError("missing")),
    )
    await provider._prefetch_format_for_track("track1")
    assert provider._normalized_params == before

async def test_prefetch_unexpected_error_propagates(self) -> None:
    provider = _make_provider()
    _stub_attr(
        provider,
        "_get_stream_details_with_retry",
        AsyncMock(side_effect=RuntimeError("bug")),
    )
    with pytest.raises(RuntimeError, match="bug"):
        await provider._prefetch_format_for_track("track1")
```

Add the same known/unexpected pairing for `_replenish_radio_queue`. Add
capability tests where `get_supported_sample_rates()` raises `ValueError`
(fallback) and `RuntimeError` (propagation) for both `_snap_rate_to_player` and
`_effective_signature_for_player`.

For dynamic prefetch, retain the existing invalid-format retry test, add a
`RetriesExhausted`-then-success test, and add `MediaNotFoundError` and
`RuntimeError` propagation tests that assert one fetch and no sleep.

- [ ] **Step 2: Run the focused tests and verify red**

Run:

```bash
uv run pytest -q tests/test_provider.py -k 'prefetch or replenish_radio or rate_snap or effective_signature or dynamic_stream_details'
```

Expected: unexpected exceptions are swallowed or retried by current broad catches.

- [ ] **Step 3: Implement narrow fallback and dynamic retry tuples**

Use `except MusicAssistantError` in ordinary prefetch and radio replenishment.
Use this exact tuple in both capability helpers:

```python
except (AttributeError, TypeError, ValueError):
```

In `_get_dynamic_stream_details`, keep the nested `ValueError` cache
invalidation and retry only:

```python
except (ResourceTemporarilyUnavailable, RetriesExhausted, ValueError) as err:
```

Keep `asyncio.CancelledError` propagation before this tuple. Do not catch
`MediaNotFoundError`, `LoginFailed`, or `Exception`.

- [ ] **Step 4: Run focused tests and verify green**

Run the command from Step 2. Expected: selected tests pass.

- [ ] **Step 5: Confirm no broad catches or generic raises remain in the scoped file**

Run:

```bash
rg -n 'except Exception|raise RuntimeError|RuntimeError\(' provider/provider.py
```

Expected: no matches.

- [ ] **Step 6: Commit Task 3**

```bash
git add provider/provider.py tests/test_provider.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "fix: restrict best-effort provider fallbacks"
```

---

### Task 4: Clarify credential ownership and document the fix

**Files:**
- Modify: `provider/credential_source.py`
- Modify: `tests/test_credential_source.py`
- Modify: `CLAUDE.local.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: the existing `YandexMusicCredentialSource.read_tokens() -> tuple[SecretStr | None, SecretStr | None]` contract.
- Produces: explicit documentation that the adapter is provider-local, reads setup data, and deliberately does not use `ya_passport_auth.ma.BorrowedCredentialSource`; behavior remains unchanged.

- [ ] **Step 1: Strengthen the existing setup-data contract test**

In `tests/test_credential_source.py`, rename the setup-data test to
`test_reads_only_setup_owned_tokens` and keep the guard that raises if
`owner.config.get_value` is called. Add a guard that `mass.config` is not used
directly, so the test requires the public provider accessor.

- [ ] **Step 2: Run the credential test and confirm it passes as a characterization test**

Run:

```bash
uv run pytest -q tests/test_credential_source.py
```

Expected: all credential-source tests pass. This step characterizes an
existing architectural invariant and intentionally does not require red.

- [ ] **Step 3: Clarify the provider-local boundary in documentation**

Update the module and class documentation in `provider/credential_source.py`
to state that the adapter owns only Music Assistant setup-data access and
never refreshes or persists tokens. Update the credential-source row and
configuration-ownership section in `CLAUDE.local.md` with the same boundary.
Do not mention private symbols in the changelog.

- [ ] **Step 4: Add the release-note entry without changing `VERSION`**

Add an `Unreleased` section at the top of `CHANGELOG.md`:

```markdown
## [Unreleased]

### Changed

- Provider failures now retain Music Assistant's specific error categories, while retries and best-effort fallbacks are limited to expected transient, player-command, and capability-data failures.

### Fixed

- Permanent authentication and missing-media failures no longer enter stream retry loops, and unexpected internal errors are no longer hidden by playback fallback paths.
```

- [ ] **Step 5: Run focused tests and documentation checks**

Run:

```bash
uv run pytest -q tests/test_credential_source.py tests/test_provider.py
uv run codespell provider/credential_source.py CLAUDE.local.md CHANGELOG.md
git diff --check
```

Expected: all tests and checks pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add provider/credential_source.py tests/test_credential_source.py CLAUDE.local.md CHANGELOG.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "docs: clarify linked credential ownership"
```

---

### Task 5: Full verification and draft PR

**Files:**
- Verify: all files changed since `dev`
- Publish: branch `fix/narrow-provider-errors`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a fully verified draft PR against `dev`, without replies or mutations to upstream PR #5589.

- [ ] **Step 1: Run the complete verification suite**

Run each command and stop on the first failure:

```bash
uv run pytest -q
uv run ruff check provider tests
uv run ruff format --check provider tests
uv run mypy provider tests
PATH="$PWD/.venv/bin:$PATH" uv run pre-commit run --all-files
git diff --check dev...HEAD
```

Expected: 0 failures and exit status 0 for every command.

- [ ] **Step 2: Review the complete diff and commit state**

Run:

```bash
git status --short --branch
git diff --stat dev...HEAD
git diff dev...HEAD
git log --oneline dev..HEAD
```

Confirm that `VERSION`, `provider/ynison_client.py`, and dependency files are unchanged and that no unrelated files are present.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin fix/narrow-provider-errors
```

- [ ] **Step 4: Open a draft PR**

Create a draft PR targeting `dev` with title:

```text
fix: narrow provider error handling
```

The body must summarize the provider-local setup-data credential boundary,
typed MA errors, transient-only retries, narrowed fallback catches, unchanged
`ya-passport-auth` dependency, and exact verification results. Do not reply to
or resolve comments in music-assistant/server PR #5589.
