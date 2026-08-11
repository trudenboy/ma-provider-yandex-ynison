# Issue #125 Shared HTTP Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Ynison WebSockets through Music Assistant's managed HTTP session, release the fix as 4.0.3, publish it to `origin/dev`, and close issue #125.

**Architecture:** `YandexYnisonProvider` injects `mass.http_session` through the existing `YnisonClient(http_session=...)` seam. `YnisonClient` keeps its current external-session ownership and reconnect behavior; no resolver, connector, IPv4, or protocol changes are added.

**Tech Stack:** Python 3.14, aiohttp, Music Assistant `PluginProvider`, pytest, unittest.mock, Ruff, mypy, pre-commit, Astro, git, GitHub CLI.

## Global Constraints

- Keep the public provider behavior and configuration schema unchanged.
- Reuse `self.mass.http_session`; do not construct a new connector or force IPv4.
- Do not change `YnisonClient` session ownership logic.
- Release version is exactly `4.0.3` with date `2026-08-11`.
- Close issue #125 only after `origin/dev` contains the fix.
- Use the exact closing comment `Fixed in 4.0.3.`
- Do not create a release tag or GitHub Release.

---

### Task 1: Inject the managed Music Assistant HTTP session

**Files:**
- Modify: `tests/test_provider.py` in `TestProviderInit`
- Modify: `provider/provider.py` in `YandexYnisonProvider.handle_async_init`

**Interfaces:**
- Consumes: `MusicAssistant.http_session: aiohttp.ClientSession` and the existing `YnisonClient(..., http_session: aiohttp.ClientSession | None = None)` constructor.
- Produces: every provider-created `YnisonClient` receives the exact shared session object owned by Music Assistant.

- [ ] **Step 1: Add the provider-level regression test**

Add this test to `TestProviderInit` in `tests/test_provider.py`:

```python
async def test_handle_async_init_uses_mass_http_session(self) -> None:
    """Ynison must reuse Music Assistant's managed HTTP session."""
    provider = _make_provider()
    shared_session = MagicMock()
    shared_session.closed = False
    _stub_attr(provider.mass, "http_session", shared_session)
    _stub_attr(
        provider,
        "_resolve_token",
        AsyncMock(return_value=SecretStr("test-token")),
    )
    await provider.handle_async_init()
    assert provider._ynison is not None

    with (
        patch(
            "provider.ynison_client.aiohttp.ClientSession",
            side_effect=AssertionError("private HTTP session created"),
        ),
        patch.object(
            provider._ynison,
            "_get_redirect_ticket",
            new_callable=AsyncMock,
            side_effect=LoginFailed("controlled stop"),
        ),
        pytest.raises(LoginFailed, match="controlled stop"),
    ):
        await provider._ynison.connect()
```

The production change that makes this test pass is the addition of the
`http_session` keyword to the real `YnisonClient` construction. Without it,
`connect()` attempts to instantiate the forbidden private session and raises
`AssertionError`.

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_provider.py::TestProviderInit::test_handle_async_init_uses_mass_http_session -q
```

Expected: FAIL with `AssertionError: private HTTP session created`.

- [ ] **Step 3: Implement the minimal provider change**

In `YandexYnisonProvider.handle_async_init`, change only the constructor call:

```python
self._ynison = YnisonClient(
    token=token,
    device_info=device_info,
    on_state_update=self._handle_ynison_state,
    logger=self.logger,
    http_session=self.mass.http_session,
    on_auth_failure=self._refresh_ynison_token,
)
```

- [ ] **Step 4: Run focused GREEN checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_provider.py::TestProviderInit::test_handle_async_init_uses_mass_http_session tests/test_ynison_client.py::TestReconnectSessionOwnership -q
.venv/bin/ruff check provider/provider.py tests/test_provider.py
.venv/bin/ruff format --check provider/provider.py tests/test_provider.py
.venv/bin/mypy
```

Expected: the new test and all external-session ownership tests pass; Ruff and mypy report no errors.

- [ ] **Step 5: Commit the behavioral fix**

```bash
git add provider/provider.py tests/test_provider.py
git commit -m "fix(ynison): reuse Music Assistant HTTP session"
```

### Task 2: Prepare patch release 4.0.3

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: the verified shared-session change from Task 1.
- Produces: package version `4.0.3` and a user-facing record of reconnect hardening.

- [ ] **Step 1: Bump the version**

Replace the sole contents of `VERSION` with:

```text
4.0.3
```

- [ ] **Step 2: Add the changelog entry**

Insert immediately above the 4.0.2 section:

```markdown
## [4.0.3] - 2026-08-11

### Fixed

- Ynison reconnects now reuse Music Assistant's managed HTTP session and resolver instead of creating a private aiohttp session, preventing the published device from remaining stuck offline after transient connection failures (#125).
```

- [ ] **Step 3: Validate release metadata**

Run:

```bash
test "$(cat VERSION)" = "4.0.3"
.venv/bin/codespell CHANGELOG.md
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit release metadata**

```bash
git add VERSION CHANGELOG.md
git commit -m "chore(release): bump to 4.0.3"
```

### Task 3: Verify, merge, publish, and close issue #125

**Files:**
- Verify: all tracked project files
- GitHub target: `trudenboy/ma-provider-yandex-ynison#125`

**Interfaces:**
- Consumes: the commits from Tasks 1 and 2 on `fix/issue-125-shared-session`.
- Produces: verified `origin/dev` containing 4.0.3 and closed issue #125.

- [ ] **Step 1: Run all release gates on the feature branch**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/mypy
.venv/bin/ruff check provider tests
.venv/bin/ruff format --check provider tests
.venv/bin/python scripts/check_method_order.py
uv lock --check
.venv/bin/codespell README.md CLAUDE.local.md CHANGELOG.md ROADMAP.md IMPLEMENTATION_PLAN.md docs-site/src/content/docs specs provider tests
npm run build --prefix docs-site
.venv/bin/pre-commit run --all-files
git diff --check
git status --short
```

Expected: 278 tests pass, every static/build gate exits 0, and the worktree is clean.

- [ ] **Step 2: Update and merge into `dev`**

Run:

```bash
git switch dev
git pull --ff-only origin dev
git merge --ff-only fix/issue-125-shared-session
```

Expected: `dev` fast-forwards to the feature-branch head without conflicts.

- [ ] **Step 3: Verify the merged result**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/mypy
.venv/bin/ruff check provider tests
.venv/bin/ruff format --check provider tests
uv lock --check
test "$(cat VERSION)" = "4.0.3"
git status -sb
```

Expected: 278 tests pass, all static gates exit 0, version is 4.0.3, and `dev` is only ahead of `origin/dev` by the intended commits.

- [ ] **Step 4: Push `dev`**

Run:

```bash
git push origin dev
```

Expected: push succeeds and `git rev-parse dev` equals `git rev-parse origin/dev`.

- [ ] **Step 5: Close issue #125 with the approved comment**

Run:

```bash
gh issue close 125 --repo trudenboy/ma-provider-yandex-ynison --comment "Fixed in 4.0.3."
```

Expected: GitHub reports issue #125 closed.

- [ ] **Step 6: Confirm publication and clean up the merged branch**

Run:

```bash
gh issue view 125 --repo trudenboy/ma-provider-yandex-ynison --json state,comments,url
git branch -d fix/issue-125-shared-session
git status -sb
```

Expected: issue state is `CLOSED`, the latest comment body is exactly `Fixed in 4.0.3.`, the feature branch is deleted, and `dev` matches `origin/dev`.
