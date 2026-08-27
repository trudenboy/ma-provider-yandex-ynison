# Port Open Reverse-Sync PRs and Release 4.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correctly port provider PRs #138, #142, #143, #147, #149, and #151, then publish and verify stable Yandex Ynison provider version 4.2.0.

**Architecture:** Preserve each existing provider PR as the provenance and review boundary, but update it from the latest `dev` and replace mechanical reverse-sync conflicts with provider-native code. Adopt one current Music Assistant dependency baseline first, then migrate source control, linked-account capacity, player-owned lifecycle, generation-safe release, and required-player setup in dependency order.

**Tech Stack:** Python 3.14, Music Assistant `dev`, `music-assistant-models`, pytest/pytest-asyncio, Ruff, mypy, pre-commit, uv, GitHub CLI, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-port-open-prs-release-4.2.0-design.md`

## Global Constraints

- Keep `ym_instance` required and preserve linked-Yandex-Music credentials only.
- Never add QR login, manual `token`/`x_token`, or provider-owned persistent credentials.
- Preserve dynamic PCM sessions, session-frozen formats, typed errors, radio replenishment, and token refresh behavior.
- Use the existing reverse-sync branches; do not open or modify anything in `music-assistant/server` or `trudenboy/ma-server`.
- Do not hand-edit generated Ruff/mypy configuration; provider PR #149 is its only source.
- Keep `VERSION` at `4.1.2` until the final maintainer release PR.
- Use red-green-refactor for every functional behavior change. Reset conflicted production hunks to the current `dev` form before running the corresponding imported tests RED.
- Run every shell command through `rtk` as required by `AGENTS.md`.
- Before every push or merge, re-check branch owner, head SHA, changed files, reviews/comments, marker count, and GitHub checks.
- Never merge a dependent PR while an earlier task's local or GitHub gate is red.

## File Responsibility Map

- `provider/provider.py`: plugin lifecycle, source controls, stream ownership, linked provider streaming, advertised name, and cleanup.
- `provider/protocols.py`: structural Yandex Music provider surface, including stream-slot ownership.
- `provider/setup_flow.py`: linked account and concrete player selection/reconfiguration.
- `provider/constants.py`: setup keys and defaults; remove Auto/free-form name constants only in #151.
- `provider/strings.json`: user-facing setup/config copy and abort/load errors.
- `tests/test_provider.py`: source control, streaming, ownership, generation, rename, and invariant regressions.
- `tests/test_setup_flow.py`: setup/reconfigure persistence and validation.
- `tests/test_config_entries.py`: runtime/setup ownership boundary.
- `uv.lock`: exact compatible Music Assistant/models/test dependency graph.
- `ruff.toml`, generated `pyproject.toml` sections: provider-tools configuration delivered by #149.
- `README.md`, `CLAUDE.local.md`: required-player and linked-credential operational contract.
- `CHANGELOG.md`: one future 4.2.0 block with observable changes only.
- `specs/done/reverse-sync-pr*.md`: completed provenance/specification records for each upstream port.

---

### Task 1: Adopt SourceControlValue and a Reproducible Dependency Baseline (#142)

**Files:**
- Modify: `provider/provider.py:35-48,444-463`
- Modify: `tests/test_provider.py` source-control tests
- Modify: `uv.lock`
- Move/modify: `specs/inprogress/reverse-sync-pr5880.md` → `specs/done/reverse-sync-pr5880.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `music_assistant.models.plugin.SourceControlValue` from a Music Assistant commit at or after upstream #6026.
- Produces: `YandexYnisonProvider.on_source_control(source_id: str, action: SourceControl, value: SourceControlValue = None) -> None`.
- Produces: a frozen environment containing `music-assistant-models==1.1.204` or a later version verified against the selected MA commit.

- [ ] **Step 1: Create an isolated worktree for the existing PR branch and preflight ownership**

Run:

```bash
rtk git fetch --prune origin
rtk gh pr view 142 --json headRefName,headRefOid,author,isDraft,files,reviews,comments,mergeable,mergeStateStatus
rtk git worktree add .worktrees/pr142 -b work/pr142 origin/reverse-sync/yandex_ynison-pr5880
rtk git -C .worktrees/pr142 merge --no-edit origin/dev
```

Expected: the remote head is `4fbc23d58b7a2d76bf4701ebe9dd574d847fa5ee`, with no human commits/reviews/comments; the merge introduces current generated wrappers but no unresolved Git index conflicts.

- [ ] **Step 2: Refresh only the Music Assistant dependency graph**

Run:

```bash
rtk uv lock --upgrade-package music-assistant --upgrade-package music-assistant-models
rtk uv sync --extra test --frozen
rtk uv run python -c "from music_assistant.models.plugin import SourceControlValue; from music_assistant.models.music_provider import MusicProvider; print(SourceControlValue, hasattr(MusicProvider, 'acquire_stream_slot'))"
```

Expected: import succeeds, `acquire_stream_slot` is `True`, and the old collection-time `hass_client` failure is gone. Review `uv.lock` to ensure only dependency-resolution changes occurred.

- [ ] **Step 3: Write RED tests for seek payload discrimination**

Add focused tests that call the real method:

```python
@pytest.mark.parametrize("value", [True, False, None])
async def test_source_control_does_not_treat_non_seek_payload_as_position(value: object) -> None:
    provider = _make_provider()
    provider._on_seek = AsyncMock()

    await provider.on_source_control(AUDIO_SOURCE_ID, SourceControl.SEEK, value)  # type: ignore[arg-type]

    provider._on_seek.assert_not_awaited()


async def test_source_control_coerces_numeric_seek_position_to_seconds() -> None:
    provider = _make_provider()
    provider._on_seek = AsyncMock()

    await provider.on_source_control(AUDIO_SOURCE_ID, SourceControl.SEEK, 12)

    provider._on_seek.assert_awaited_once_with(12)
```

- [ ] **Step 4: Run the focused tests and confirm RED**

Run:

```bash
rtk uv run pytest tests/test_provider.py -k 'source_control and (position or payload)' -vv
```

Expected: boolean cases fail because the old `value is not None` condition forwards `True`/`False` to `_on_seek`.

- [ ] **Step 5: Implement the minimal source-control adapter**

Import `SourceControlValue`, update the override signature, and use this exact guard:

```python
elif (
    action == SourceControl.SEEK
    and isinstance(value, (int, float))
    and not isinstance(value, bool)
):
    await self._on_seek(int(value))
```

Do not add Spotify-only shuffle/repeat behavior; Ynison does not declare those capabilities.

- [ ] **Step 6: Verify GREEN and the full refreshed baseline**

Run:

```bash
rtk uv run pytest tests/test_provider.py -k 'source_control and (position or payload)' -vv
rtk uv run pytest
rtk uv run ruff check provider tests
rtk uv run ruff format --check provider tests
rtk uv run mypy
```

Expected: focused tests pass; the full suite collects and passes on the refreshed lock.

- [ ] **Step 7: Complete the PR record and changelog**

Replace the reverse-sync scaffold with a completed specification containing upstream PR #5880, accepted payloads, boolean rejection, compatibility floor, and the focused/full test commands. Move it to `specs/done/`. Remove its old `Reverse-synced ... (WIP)` line and create `## [4.2.0] - 2026-08-27` with a canonical `### Changed` bullet describing compatibility with current Music Assistant source controls.

- [ ] **Step 8: Run final branch gates and commit**

Run:

```bash
rtk rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' provider tests specs CHANGELOG.md
rtk git diff --check
rtk uv run pre-commit run --all-files
rtk uv run git commit -am 'fix: adopt current audio source control payloads'
```

Stage the moved spec and `uv.lock` explicitly if not covered by `-a`.

- [ ] **Step 9: Push, verify CI, and merge #142**

Push `work/pr142` to `reverse-sync/yandex_ynison-pr5880`, mark ready only after checks exist, update the PR body with actual tests/compatibility, and remove no provenance. Re-read the pushed head and all checks, then squash-merge #142 without deleting unrelated branches. Fetch `origin/dev` and verify the merge commit contains the reviewed head's tree.

---

### Task 2: Merge Generated Wrapper Configuration (#149)

**Files:**
- Existing generated changes only: `pyproject.toml`, `ruff.toml`

**Interfaces:**
- Consumes: the #142 `SourceControlValue` override so upstream mypy succeeds.
- Produces: provider-tools-owned lint/type configuration matching current upstream MA.

- [ ] **Step 1: Re-preflight #149 and update it from merged `dev`**

Confirm head `cfae181a59ca19d1dcad27637a5705ecab80836d`, author, exact two-file diff, no comments/reviews, and config-sync provenance. Create `.worktrees/pr149`, merge current `origin/dev`, and verify `git diff origin/dev...HEAD` still changes only generated config.

- [ ] **Step 2: Run generated-config and full gates**

Run:

```bash
rtk uv sync --extra test --frozen
rtk uv run ruff check provider tests
rtk uv run ruff format --check provider tests
rtk uv run mypy
rtk uv run pytest
rtk uv run pre-commit run --all-files
rtk git diff --check
```

Expected: the previous `on_source_control` type error is absent. This task has no TDD cycle because it changes generated configuration, not production behavior; the approved design explicitly reserves these files to provider-tools.

- [ ] **Step 3: Push, verify, and merge #149**

Commit only the merge/update if needed, push the existing branch, wait for config-sync plus provider tests/type checks, then squash-merge #149. Verify its two-file generated delta on `origin/dev`.

---

### Task 3: Charge Streaming to the Linked Yandex Music Account (#138)

**Files:**
- Modify: `provider/protocols.py`
- Modify: `provider/provider.py` stream generator, retry/cache helpers, provider matching
- Modify: `tests/test_provider.py` linked-provider streaming tests
- Move/modify: `specs/inprogress/reverse-sync-pr5773.md` → `specs/done/reverse-sync-pr5773.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `MusicProvider.acquire_stream_slot(wait_timeout: float | None) -> AbstractAsyncContextManager[None]` and `STREAM_SLOT_PLAYBACK_WAIT_TIMEOUT`.
- Produces: `YandexMusicProviderLike.instance_id`, `.available`, `.get_quality()`, `.acquire_stream_slot()`, `.get_stream_details()`, and `.get_audio_stream()`.
- Produces: `_get_stream_details_with_retry(track_id, media_type=MediaType.TRACK, *, provider: YandexMusicProviderLike | None = None) -> StreamDetails`.

- [ ] **Step 1: Create/preflight the #138 worktree and merge current `dev`**

Confirm the bot head `39ff44c1c3109582be7f6530820d09bf4d01ff58`, six committed marker blocks, and no human changes. Create `.worktrees/pr138`, merge `origin/dev`, then reset only conflicted production regions to their current `dev` implementation while retaining/adapting the upstream tests for RED.

- [ ] **Step 2: Write RED tests for exact account ownership and slot lifetime**

Use an async context manager recording entry/exit:

```python
@asynccontextmanager
async def slot() -> AsyncIterator[None]:
    events.append("enter")
    try:
        yield
    finally:
        events.append("exit")

ym.instance_id = "ym-inst"
ym.available = True
ym.acquire_stream_slot.side_effect = slot
```

Cover: slot wraps raw stream consumption; early generator close records `exit`; a provider swap stops streaming; cache keys include `ym-inst`; cached `StreamDetails.provider != ym-inst` is discarded; owner mismatch raises `_StreamOwnerMismatchError` and is not retried as transient.

- [ ] **Step 3: Run the capacity tests and confirm RED**

Run:

```bash
rtk uv run pytest tests/test_provider.py -k 'stream_slot or linked_provider or stream_owner or cache_key' -vv
```

Expected: missing `acquire_stream_slot`, provider-insensitive cache, and generator finalization assertions fail against the reset production implementation.

- [ ] **Step 4: Implement the minimal linked-provider capacity boundary**

Add `instance_id`, `available`, and `acquire_stream_slot` to the protocol while retaining `get_quality`. Capture `provider = self._yandex_provider` before awaits; verify identity and availability after each await. Key stream-detail cache as `ynison_sd_{provider_instance_id}_{track_id}` and reject mismatched owners. Wrap both the per-track generator and raw/ffmpeg generators in `aclosing`; acquire the linked provider's slot only around actual raw stream reading.

Preserve the current retry contract: `_StreamOwnerMismatchError`, authentication, missing media, and other permanent `MusicAssistantError` subclasses must escape; only the existing transient category receives retry/backoff.

- [ ] **Step 5: Verify GREEN plus regression suites**

Run the focused command, then:

```bash
rtk uv run pytest tests/test_provider.py tests/test_credential_source.py tests/test_auth.py -vv
rtk uv run pytest
rtk uv run ruff check provider tests
rtk uv run ruff format --check provider tests
rtk uv run mypy
```

- [ ] **Step 6: Complete spec/changelog, remove markers, commit, and merge**

Document exact account ownership and slot lifetime in the completed spec. Add a 4.2.0 `### Fixed` or `### Changed` bullet stating that Ynison playback now observes the linked account's concurrency limit. Run marker scan, `git diff --check`, and full pre-commit; commit, push to the existing branch, remove `needs-human` only after the scan is empty, make ready, verify fresh CI, and squash-merge #138.

---

### Task 4: Move AudioSource Ownership from Queue to Player (#143)

**Files:**
- Modify: `provider/provider.py` ownership field and lifecycle callbacks
- Modify: `tests/test_provider.py` selection, release, pause, capabilities, dynamic-session tests
- Move/modify: `specs/inprogress/reverse-sync-pr5914.md` → `specs/done/reverse-sync-pr5914.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `PluginProvider.on_source_selected(source_id, player_id, owner_player_id, stream_session_id)`.
- Produces: `_in_use_by_player: str | None` and player-owned source refresh/release behavior.
- Preserves: `_active_player_id` as the actual consuming player/bridge and `_active_session_id` as the stale-request token.

- [ ] **Step 1: Preflight #143, merge current `dev`, and remove imported production markers**

Confirm head `df31cdaa95fe6981acdb891ee5e3c01fceb17b59`, five marker blocks, and the lack of human changes. Keep the upstream lifecycle tests, reset conflicted production regions to current `dev`, and ensure the marker scan is empty before RED.

- [ ] **Step 2: Add RED player-ownership regressions**

Tests must prove:

```python
await provider.on_source_selected("main", "bridge-player", "owner-player", "session-1")
assert provider._active_player_id == "bridge-player"
assert provider._in_use_by_player == "owner-player"
```

Also execute the active-player switching path that previously referenced undefined `queue_id`; verify `deselect_source("owner-player")` rather than stopping/releasing the bridge; verify stale session ids do not clear a newer claim; verify `_update_source_capabilities` calls `mass.players.refresh_source(owner_player_id, source)`; verify dynamic format restart preserves the replacement session.

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```bash
rtk uv run pytest tests/test_provider.py -k 'source_selected or source_unselected or source_capabilities or clear_active_player or dynamic' -vv
```

Expected: ownership attribute/signature assertions and the active-player path fail against queue-owned production code.

- [ ] **Step 4: Implement player-owned lifecycle**

Rename `_in_use_by_queue` to `_in_use_by_player` throughout real ownership checks. Treat `owner_player_id` as the source-session owner and `player_id` as the physical/protocol consumer. Remove every runtime reference to the deleted local `queue_id`. Refresh capabilities through `mass.players.refresh_source`. When clearing, deselect the source from its owner; do not clear a newer `_active_session_id` or dynamic generation.

- [ ] **Step 5: Verify GREEN and full gates**

Run the focused command, all dynamic-format tests, full pytest, Ruff, mypy, marker scan, `git diff --check`, and pre-commit.

- [ ] **Step 6: Complete provenance, push, and merge #143**

Complete/move its spec, add a 4.2.0 `### Changed` bullet that external Ynison playback no longer replaces the player's queue, commit and push. Remove `needs-human` only after fresh validation, then verify and squash-merge the reviewed SHA.

---

### Task 5: Guard Stale Source Releases by Playback Generation (#147)

**Files:**
- Modify: `provider/provider.py:_clear_active_player`
- Modify: `tests/test_provider.py:TestClearActivePlayer`
- Move/modify: `specs/inprogress/reverse-sync-pr5944.md` → `specs/done/reverse-sync-pr5944.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `mass.players.get_audio_source_session(owner_player_id)` returning a session with `playback_session_id`.
- Consumes: `mass.players.deselect_source(owner_player_id, *, provider_instance_id, source_id, playback_session_id)`.
- Produces: cleanup scoped to this provider, source `main`, and the captured playback session.

- [ ] **Step 1: Preflight #147 and merge the #143-based `dev`**

Confirm head `d328fa6ebe249f52318329f564265045594596f7`, three marker blocks, no human delta, then merge current `origin/dev`. Reset the production cleanup hunk to #143's merged form while retaining the upstream generation tests.

- [ ] **Step 2: Write/verify RED generation tests**

Pin the exact call:

```python
provider.mass.players.get_audio_source_session.return_value.playback_session_id = "generation-7"
provider._clear_active_player()
provider.mass.players.deselect_source.assert_called_once_with(
    "owner-player",
    provider_instance_id=provider.instance_id,
    source_id=AUDIO_SOURCE_ID,
    playback_session_id="generation-7",
)
```

Also cover no owner, missing session, and owner differing from the consuming bridge. Run `pytest tests/test_provider.py -k clear_active_player -vv`; expected RED is an unscoped one-argument `deselect_source` call.

- [ ] **Step 3: Implement scoped release and verify GREEN**

Capture the source session before clearing local fields, pass its generation plus provider/source identity to `deselect_source`, and keep `None` when no session exists so core performs the documented guarded no-op. Run focused/full pytest, Ruff, mypy, marker scan, diff check, and pre-commit.

- [ ] **Step 4: Complete spec/changelog, push, and merge #147**

Add a 4.2.0 `### Fixed` bullet for delayed cleanup no longer releasing replacement playback. Complete/move the spec, remove `needs-human` after validation, push, verify the exact CI SHA, and squash-merge.

---

### Task 6: Require a Concrete Player and Derive the Ynison Name (#151)

**Files:**
- Modify: `provider/constants.py`
- Modify: `provider/provider.py` initialization/load/name/reload/target lookup
- Modify: `provider/setup_flow.py`
- Modify: `provider/strings.json`
- Modify: `tests/test_provider.py`
- Modify: `tests/test_setup_flow.py`
- Modify: `tests/test_config_entries.py`
- Modify: `README.md`
- Modify: `CLAUDE.local.md`
- Move/modify: `specs/inprogress/reverse-sync-pr6026.md` → `specs/done/reverse-sync-pr6026.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `create_player_selector(mass, key, default_value)` without an Auto sentinel.
- Consumes: player lookup/config name and player event subscription from current MA.
- Produces: required `CONF_MASS_PLAYER_ID`, no `CONF_PUBLISH_NAME`, no valid `PLAYER_ID_AUTO`, and `_display_name` derived from the configured player.
- Preserves: `CONF_YM_INSTANCE`, `LEGACY_AUTH_KEYS`, `LEGACY_YM_INSTANCE_OWN`, `YandexMusicCredentialSource`, and `missing_dependency` setup abort.

- [ ] **Step 1: Preflight #151, merge current `dev`, and isolate valid upstream intent**

Confirm head `78906d29d0553c0c92a422a223d3a6fb7068029a`, 28 marker blocks, bot-only history, no review/comments. Merge current `origin/dev`. Discard all imported own-auth/QR/manual-token hunks and undefined names (`CONF_TOKEN`, `CONF_X_TOKEN`, `CONF_REMEMBER_SESSION`, `YM_INSTANCE_OWN`, `_qr_login`, `YaPassportError`). Reset production files to current `dev` before adding setup tests.

- [ ] **Step 2: Write RED setup tests**

Add real setup-session tests for:

```python
await run_setup(session)
form = session.forms[-1]
assert {entry.key for entry in form.entries} == {CONF_YM_INSTANCE, CONF_MASS_PLAYER_ID}
assert form.entry(CONF_MASS_PLAYER_ID).required is True
assert form.entry(CONF_MASS_PLAYER_ID).value != "__auto__"
```

Cover: `AbortFlow("no_players")` when no player exists; `AbortFlow("missing_dependency")` when no linked Yandex Music provider exists; sole linked account auto-selection; multiple-account selector; reconfigure of legacy own-auth data clearing `LEGACY_AUTH_KEYS`; submitted data containing only linked instance and concrete player; no free-form name or QR step.

- [ ] **Step 3: Run setup tests and confirm RED**

Run:

```bash
rtk uv run pytest tests/test_setup_flow.py tests/test_config_entries.py -vv
```

Expected: current setup exposes Auto and `publish_name`, and does not abort when no players are available.

- [ ] **Step 4: Implement the minimal linked-only setup flow**

Keep `list_yandex_music_instances` and `missing_dependency`. Abort `no_players` when the player registry is empty. Use the player selector without `PLAYER_ID_AUTO`; persist only `CONF_YM_INSTANCE` and `CONF_MASS_PLAYER_ID` plus legacy null-clearing keys during reconfigure. Remove `CONF_PUBLISH_NAME`, `PLAYER_ID_AUTO`, and their strings only when all references are eliminated.

- [ ] **Step 5: Verify setup GREEN**

Run the Step 3 command and confirm all setup/config ownership tests pass.

- [ ] **Step 6: Write RED provider-load and rename tests**

Cover: provider load fails with `SetupFailedError(translation_key="no_connected_player")` when no concrete configured player exists; `_get_target_player_id` never auto-selects; `_display_name` returns current player `display_name`, falls back to stored `name`/`default_name` on cold boot, then `DEFAULT_DISPLAY_NAME`; a player rename schedules exactly one reload only when it differs from `_advertised_name`.

- [ ] **Step 7: Run provider-name tests and confirm RED**

Run:

```bash
rtk uv run pytest tests/test_provider.py -k 'connected_player or advertised_name or display_name or target_player' -vv
```

Expected: Auto fallback/free-form `_display_name` behavior fails the new assertions.

- [ ] **Step 8: Implement required-player load and derived naming**

Store `_default_player_id` as the configured concrete id or empty string and `_advertised_name: str | None`. During load, raise translated `SetupFailedError` if no setup value exists. Build `YnisonDeviceInfo.title` from the selected player's display/config name. Subscribe to added/config-updated/player-updated events filtered by the connected player, and schedule a provider reload only when the effective name changes. Remove `instance_name_postfix`; keep multi-instance identity unchanged.

- [ ] **Step 9: Verify GREEN and invariants**

Run focused setup/provider tests, then explicitly run credential, dynamic format, radio, and error suites before full pytest:

```bash
rtk uv run pytest tests/test_setup_flow.py tests/test_config_entries.py tests/test_credential_source.py tests/test_auth.py tests/test_format_policy.py tests/test_provider.py -vv
rtk uv run pytest
rtk uv run ruff check provider tests
rtk uv run ruff format --check provider tests
rtk uv run mypy
```

- [ ] **Step 10: Update strings and documentation**

Make setup copy say “linked Yandex Music account and target player”; add `no_players` and `no_connected_player`; remove Auto/published-name copy and all QR errors. Update README and `CLAUDE.local.md` tables/flows to state that one real player is mandatory and its current name is advertised. Retain linked credential and dynamic PCM sections verbatim except where the ownership term changes from queue to player.

- [ ] **Step 11: Complete spec/changelog, validate, push, and merge #151**

Complete/move the #6026 spec. Add 4.2.0 `### Changed` and `### Removed` bullets for concrete player selection and removal of Auto/free-form naming. Run JSON validation, marker/obsolete-symbol scans, all gates, and pre-commit. Remove `needs-human`, mark ready, push, verify fresh CI at the exact head, and squash-merge.

---

### Task 7: Cross-PR Standards and Spec Review

**Files:**
- Review the full `origin/dev` range from the pre-port `af2d17057a47e2f193d0a73ca97409a25e0c0876` through merged #151.

**Interfaces:**
- Consumes: all six merged provider PRs.
- Produces: a standards/spec audit with every material finding fixed before release.

- [ ] **Step 1: Run the repository code-review workflow**

Use the `code-review` skill against fixed point `af2d17057a47e2f193d0a73ca97409a25e0c0876`, with Standards and Spec axes. Verify method order, typed errors, linked-only auth, dynamic-session ownership, complete specs, changelog structure, and absence of generated-config drift.

- [ ] **Step 2: Convert every valid finding into RED→GREEN fixes**

For each behavioral finding, add a focused failing regression, confirm RED, implement the smallest fix in the owning PR branch or a dedicated pre-release fix PR, and confirm GREEN. Do not silently waive findings; record rejected findings with exact code evidence.

- [ ] **Step 3: Run the complete pre-release gate**

Run on fresh `origin/dev`:

```bash
rtk uv sync --extra test --frozen
rtk uv run pytest
rtk uv run ruff check provider tests
rtk uv run ruff format --check provider tests
rtk uv run mypy
rtk uv run pre-commit run --all-files
rtk git diff --check
rtk rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)|Reverse-synced upstream PR|\(WIP\)|CONF_PUBLISH_NAME|PLAYER_ID_AUTO|_in_use_by_queue|_qr_login|YaPassportError' provider tests specs CHANGELOG.md README.md CLAUDE.local.md
```

Expected: all commands exit zero; the final scan returns no matches except historical prose that is reviewed and explicitly valid.

---

### Task 8: Create and Merge the Maintainer Release PR for 4.2.0

**Files:**
- Modify: `VERSION`
- Final review/modify: `CHANGELOG.md`
- Final review/modify: `README.md`, `CLAUDE.local.md`
- Include: design and implementation plan documents if they have not landed through an earlier PR

**Interfaces:**
- Consumes: fully green `origin/dev` after #151 and review fixes.
- Produces: `VERSION == 4.2.0` matching one changelog release block dated `2026-08-27`.

- [ ] **Step 1: Create a release branch/worktree from the verified `origin/dev`**

Run:

```bash
rtk git fetch origin dev
rtk git worktree add .worktrees/release-4.2.0 -b release/4.2.0 origin/dev
```

- [ ] **Step 2: Set the exact version and audit release notes**

Change `VERSION` from `4.1.2` to `4.2.0` with `apply_patch`. Ensure there is exactly one `## [4.2.0] - 2026-08-27` block, canonical heading order, no internal symbols/paths/process noise, and no edits to historical release blocks.

- [ ] **Step 3: Run fresh release-candidate verification**

Run the complete pre-release gate from Task 7 and additionally:

```bash
rtk test "$(rtk cat VERSION)" = '4.2.0'
rtk git tag --list v4.2.0
rtk gh release view v4.2.0
```

Expected before merge: version assertion passes; tag/release lookups report not found, proving the version is not already published.

- [ ] **Step 4: Commit, push, and open the release PR**

Commit `release: 4.2.0`, push `release/4.2.0`, and open a PR to `dev` summarizing all six provider PRs, compatibility floor, user-visible setup change, exact local verification, and rollback-as-forward-patch policy. Request/confirm maintainer Code Owner approval for `VERSION`.

- [ ] **Step 5: Verify CI and merge the reviewed release SHA**

Re-check files, reviews, comments, head SHA, required checks, `mergeable`, and `mergeStateStatus`. Merge only after all checks are green and Code Owner approval is present. Fetch `origin/dev` and confirm `VERSION` and changelog at the merged commit.

---

### Task 9: Verify Published Release and Durable Synchronization

**Files:**
- No repository changes unless verification reveals a defect requiring a forward patch release.

**Interfaces:**
- Consumes: merged release commit on `dev`.
- Produces: evidence for tag, GitHub Release/assets, pipeline gate, integration sync, and stable upstream sync.

- [ ] **Step 1: Watch the exact pipeline run to completion**

Resolve the workflow run triggered by the release merge SHA, then use `rtk gh run watch <run-id> --exit-status`. Do not accept a successful manual dispatch for a different SHA as evidence.

- [ ] **Step 2: Verify tag and GitHub Release**

Run:

```bash
rtk gh release view v4.2.0 --json tagName,isDraft,isPrerelease,publishedAt,assets,url,targetCommitish
rtk git fetch --tags origin
rtk git rev-list -n 1 v4.2.0
rtk git rev-parse origin/dev
```

Confirm stable/non-draft metadata, required provider archive assets, and that the tag represents the reviewed release tree.

- [ ] **Step 3: Verify both sync outcomes**

Inspect the pipeline jobs and the integration fork branches/workflow outputs. Confirm every provider file plus `VERSION` and manifest has a durable representation in `integration/dev` and `upstream/yandex_ynison`; do not infer synchronization from workflow dispatch acceptance alone.

- [ ] **Step 4: Perform post-release provider smoke verification**

Start the documented test Compose instance from the released tree, verify container state/logs/HTTP readiness, load a Ynison instance with a linked Yandex Music provider and concrete player, and exercise setup plus source registration/control. Record real external-account/player limitations separately from automated results; do not claim live Yandex/physical playback unless actually observed.

- [ ] **Step 5: Close the task only with evidence**

Report merged PR numbers and SHAs, total tests, all gate conclusions, release/tag URL and SHA, asset names, sync destinations, smoke result, and any unverified real-device boundary. If publication partially failed, diagnose existing artifacts before retrying and never delete/rewrite v4.2.0.
