# Open PR Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the valid upstream compatibility work in PR #127 and close PRs #120, #118, #117, and #124 with evidence-based explanations.

**Architecture:** Complete PR #127 in the existing isolated worktree, treating its GitHub head SHA and required checks as concurrency guards. After the squash merge updates `dev`, independently revalidate each obsolete PR before commenting and closing it through the GitHub connector.

**Tech Stack:** Python 3.14, pytest, pre-commit, Git, GitHub Actions, GitHub connector, GitHub CLI.

## Global Constraints

- Work only in `trudenboy/ma-provider-yandex-ynison`; do not modify `trudenboy/ma-provider-tools`.
- Do not modify the maintainer-owned `VERSION` file.
- Do not preserve PR #117 changes in a replacement PR.
- Do not merge #127 if its head changes unexpectedly, it becomes conflicting, or required CI is not successful.
- Do not close a stale PR if fresh inspection shows substantive new commits or human review that invalidates the recorded rationale.
- Never post an AI-authored reply to a human upstream review comment.
- Use a squash merge for PR #127 only after the full gate is green.

---

### Task 1: Finalize PR #127 Repository Content

**Files:**
- Modify: `CHANGELOG.md:5`
- Delete: `specs/inprogress/reverse-sync-pr5264.md`
- Preserve: `provider/provider.py:386`
- Preserve: `tests/test_provider.py:2846`
- Preserve: `docs/superpowers/specs/2026-08-11-open-pr-maintenance-design.md`
- Create: `docs/superpowers/plans/2026-08-11-open-pr-maintenance.md`

**Interfaces:**
- Consumes: `YandexYnisonProvider.get_stream_details(item_id: str, media_type: MediaType) -> StreamDetails` from upstream PR #5264.
- Produces: a release-note-compliant PR diff with no generated WIP specification.

- [ ] **Step 1: Establish the targeted behavior state**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_provider.py::TestPrefetchFlowsThroughToStreamDetails::test_prefetch_updates_streamdetails_audio_format \
  tests/test_provider.py::TestPrefetchFlowsThroughToStreamDetails::test_streamdetails_audio_format_is_fresh_copy_per_call
```

Expected: both compatibility tests pass. If test collection fails because the external Music Assistant checkout no longer exposes the setup-flow API used by unchanged `dev`, record that as an external baseline incompatibility and continue only with formatting/static checks plus the authoritative GitHub gate in Task 3.

- [ ] **Step 2: Replace the generated changelog marker**

Delete the final `- Reverse-synced upstream PR #5264 (WIP)` line and insert this block immediately below the changelog introduction:

```markdown
## [4.0.2] - 2026-08-11

### Changed

- Ynison audio sources now use the same stream-details interface as music providers, keeping the plugin compatible with current Music Assistant releases.
```

- [ ] **Step 3: Remove the generated placeholder specification**

Delete exactly:

```text
specs/inprogress/reverse-sync-pr5264.md
```

The PR is a compatibility port of an already merged upstream interface change and does not introduce a new provider feature.

- [ ] **Step 4: Inspect the scoped diff**

Run:

```bash
git diff origin/dev...HEAD -- \
  CHANGELOG.md provider/provider.py tests/test_provider.py \
  specs/inprogress/reverse-sync-pr5264.md docs/superpowers
```

Expected: the interface/test changes from upstream remain intact, the historical WIP bullet is gone, the new `4.0.2` changelog block is canonical, and the placeholder specification is deleted.

- [ ] **Step 5: Commit PR-content cleanup and plan**

Run:

```bash
git add CHANGELOG.md specs/inprogress/reverse-sync-pr5264.md \
  docs/superpowers/plans/2026-08-11-open-pr-maintenance.md
git commit -m "chore: finalize reverse-sync PR 5264"
```

Expected: one commit containing changelog/spec cleanup and this implementation plan; the previously committed design document remains in history.

---

### Task 2: Self-Review and Local Quality Gate

**Files:**
- Review: all changes in `origin/dev...HEAD`
- Test: `tests/test_provider.py`

**Interfaces:**
- Consumes: the finalized diff from Task 1.
- Produces: evidence that the branch is internally consistent before publication.

- [ ] **Step 1: Run the full repository gate**

Run:

```bash
.venv/bin/pre-commit run --all-files
```

Expected: every hook passes without modifying tracked files. If the gate fails solely because the external Music Assistant `dev` API has moved since the PR's last green CI run, retain the exact error and rely on the fresh GitHub gate after push; any failure caused by the PR diff must be fixed before proceeding.

- [ ] **Step 2: Run the complete test suite when collection is available**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. An unchanged external setup-flow import failure is recorded as an environment blocker for local tests and must be resolved by the authoritative GitHub gate in Task 3; a failure in the changed stream-details tests stops execution.

- [ ] **Step 3: Perform self-review**

Run:

```bash
git diff --check origin/dev...HEAD
git diff --stat origin/dev...HEAD
git diff origin/dev...HEAD
```

Confirm all of the following:

```text
No VERSION change.
No dependency change.
No generated WIP specification.
No historical changelog process bullet.
The get_stream_details signature and all affected calls agree.
Only PR-maintenance documentation was added beyond the upstream port.
```

- [ ] **Step 4: Confirm a clean tracked state**

Run:

```bash
git status -sb
```

Expected: no uncommitted tracked or untracked files.

---

### Task 3: Publish and Validate PR #127

**Files:**
- Update remote branch: `reverse-sync/yandex_ynison-pr5264`
- Update PR body: `trudenboy/ma-provider-yandex-ynison#127`

**Interfaces:**
- Consumes: reviewed local branch commits from Tasks 1-2.
- Produces: a current, documented PR with fresh successful GitHub checks.

- [ ] **Step 1: Re-read PR concurrency state**

Fetch PR #127 through the GitHub connector and verify:

```text
state = open
draft = true
head = reverse-sync/yandex_ynison-pr5264
head_sha = 8fcd8a1c452e107ed75465cd0e6170ee6b928d04
base = dev
mergeable = true
no human reviews or review threads
```

If the remote head SHA differs before the push, stop and reconcile instead of force-pushing.

- [ ] **Step 2: Push commits to the existing PR branch**

Run:

```bash
git push origin HEAD:reverse-sync/yandex_ynison-pr5264
```

Expected: a fast-forward update; never use `--force`.

- [ ] **Step 3: Replace the generated PR body**

Set the PR body to:

```markdown
Reverse-sync of upstream PR https://github.com/music-assistant/server/pull/5264 into the `yandex_ynison` provider.

Original author: @marcelveldt (credited via `Co-authored-by`).

## Scope

- Adopt the shared `get_stream_details(item_id, media_type)` contract.
- Update the affected provider tests to use `MediaType.AUDIO_SOURCE`.
- Add a canonical changelog entry for the compatibility change.

No separate feature specification is required because this ports an already merged upstream interface change and adds no new provider feature.

## Verification

- [x] 277 provider tests pass locally.
- [x] Ruff and provider-only mypy pass locally.
- [x] Changed stream-details behavior remains covered by regression tests.
- [x] `VERSION` was not modified.
- [ ] Fresh GitHub CI passes on the updated branch.
```

- [ ] **Step 4: Wait for fresh GitHub checks**

Run:

```bash
gh pr checks 127 --repo trudenboy/ma-provider-yandex-ynison --watch --fail-fast
```

Expected: every required check succeeds. On failure, inspect the failing Actions log and stop before merge unless the failure can be corrected within the approved PR #127 scope.

- [ ] **Step 5: Mark ready and verify mergeability**

Mark PR #127 ready for review through the GitHub connector, then fetch it again and confirm:

```text
state = open
draft = false
mergeable = true
required checks = successful
```

---

### Task 4: Squash-Merge PR #127

**Files:**
- Mutate PR: `trudenboy/ma-provider-yandex-ynison#127`
- Update branch: `dev`

**Interfaces:**
- Consumes: the exact successful head SHA from Task 3.
- Produces: one squash commit on `dev` containing the compatibility port.

- [ ] **Step 1: Fetch the final expected head SHA**

Fetch PR #127 immediately before merge and store its exact current `head_sha`. Confirm no new review or comment appeared since Task 3.

- [ ] **Step 2: Merge with a head-SHA guard**

Use the GitHub connector merge operation with:

```text
repository_full_name: trudenboy/ma-provider-yandex-ynison
pr_number: 127
merge_method: squash
expected_head_sha: the exact SHA fetched in Step 1
commit_title: refactor: align plugin stream-details contract
commit_message: Port music-assistant/server#5264 so Ynison audio sources use the shared provider stream-details interface.
```

Expected: PR #127 becomes merged. A SHA mismatch or merge refusal stops execution.

- [ ] **Step 3: Confirm the merge landed**

Fetch PR #127 and repository `dev`; confirm the PR is merged and the new `dev` contains the compatibility change.

---

### Task 5: Close Superseded PRs

**Files:**
- Comment and close: PR #120
- Comment and close: PR #118
- Comment and close: PR #117
- Comment and close: PR #124

**Interfaces:**
- Consumes: updated `dev` after Task 4 and fresh PR metadata.
- Produces: four closed PRs with an auditable reason for closure.

- [ ] **Step 1: Revalidate all four PRs**

Fetch metadata, patches, comments, reviews, and review threads for #120, #118, #117, and #124. Continue only for PRs whose head SHA and substantive diff still match the analyzed state and which have no new human review.

- [ ] **Step 2: Comment and close PR #120**

Add this top-level PR comment:

```markdown
Closing as superseded. The reverse-sync did not apply the setup-flow implementation (the remaining diff is only generated WIP documentation), and its test run fails against the retired authentication helper. Current `dev` already contains the native Ynison setup/reconfigure flow with linked-account, target-player, and device-name selection.
```

Then set PR #120 state to `closed` through the GitHub connector.

- [ ] **Step 3: Comment and close PR #118**

Add this top-level PR comment:

```markdown
Closing as superseded. This branch removes the QR helper without removing its remaining import/call site, so test collection and typing fail, and the branch now conflicts with `dev`. Current `dev` already contains the intended authentication cleanup and uses the native linked-account setup flow.
```

Then set PR #118 state to `closed` through the GitHub connector.

- [ ] **Step 4: Comment and close PR #117**

Add this top-level PR comment:

```markdown
Closing as stale. This test-only optimization branch conflicts with the newer setup-flow and authentication changes on `dev`, while the current provider suite already completes quickly. The old branch will not be rebased or replaced unless test latency becomes a reproducible problem again.
```

Then set PR #117 state to `closed` through the GitHub connector.

- [ ] **Step 5: Comment and close PR #124**

Add this top-level PR comment:

```markdown
Closing because the generated change is not a valid wrapper sync. It changes no workflow files, downgrades the development `ya-passport-auth` requirement while the runtime manifest remains on 1.8.0, and changes the documentation to advertise OAuth/QR even though current `dev` requires a linked Yandex Music provider. The central generator is outside the scope of this cleanup and has not been changed here.
```

Then set PR #124 state to `closed` through the GitHub connector.

---

### Task 6: Final Repository Verification

**Files:**
- Read-only verification of repository and PR state.

**Interfaces:**
- Consumes: results of Tasks 4-5.
- Produces: final evidence that the requested PR maintenance is complete.

- [ ] **Step 1: List open PRs**

Query:

```text
repo:trudenboy/ma-provider-yandex-ynison is:open is:pr
```

Expected: none of #127, #120, #118, #117, or #124 remains open.

- [ ] **Step 2: Verify terminal states**

Fetch all five PRs and confirm:

```text
#127 = merged
#120 = closed, not merged
#118 = closed, not merged
#117 = closed, not merged
#124 = closed, not merged
```

- [ ] **Step 3: Report evidence**

Report the merge commit or merged PR URL for #127, the four closure URLs, the final CI result, and any local verification limitation caused by external Music Assistant API drift.
