# Current-Codebase Documentation Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every maintained document describe the stable 4.0.2 AudioSource implementation and remove obsolete current-state guidance.

**Architecture:** Treat `VERSION`, `provider/manifest.json`, and provider constants/implementation as factual sources of truth. Update documentation in cohesive groups, preserve genuinely historical material, and validate built artifacts and structure instead of adding brittle prose-text tests.

**Tech Stack:** Markdown, Astro/Starlight, Python 3.14, Ruff, codespell, Git.

## Global Constraints

- Do not modify production Python, dependencies, `VERSION`, the manifest, workflows, or runtime behavior.
- Describe only the shipped `AudioSource` stream path.
- Every Ynison instance links to exactly one configured `yandex_music` provider.
- The lossless no-hint floor is 24-bit/44.1 kHz; hints may lift it and player capabilities may snap it down.
- Ordinary Ynison disconnects recover automatically with saturated 5/10/30/60-second backoff and jitter.
- Preserve historical spec explanations when clearly framed as prior state.
- Do not add source-text pytest assertions for human prose.
- Report the known `uv.lock`/Music Assistant API mismatch; do not fix it here.

---

### Task 1: Update the Core English Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.local.md`

**Interfaces:**
- Consumes: `VERSION`, `provider/manifest.json`, `provider/constants.py`, `provider/streaming.py`, `provider/provider.py`, and `provider/ynison_client.py`.
- Produces: current user landing page and maintainer architecture guide.

- [ ] Preserve the generated README header block and rewrite the remaining README around stable status, AudioSource, linked credentials, setup/reconfigure, PCM behavior, reconnect, control delivery, and radio replenishment.
- [ ] Rewrite `CLAUDE.local.md` with current architecture, invariants, modules, setup/runtime configuration, credential lifecycle, session ownership, recovery semantics, radio queues, and verification boundaries.
- [ ] Remove the handoff FSM, old auth actions, `PluginSource` current-state terminology, obsolete versions, and personal absolute paths.
- [ ] Run:

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/codespell README.md CLAUDE.local.md
git diff --check
```

Expected: all commands exit zero.

- [ ] Commit:

```bash
git add README.md CLAUDE.local.md
git commit -m "docs: align core guides with AudioSource implementation"
```

---

### Task 2: Update the Russian Documentation Site

**Files:**
- Modify: `docs-site/src/content/docs/index.md`
- Modify: `docs-site/src/content/docs/configuration.md`
- Modify: `docs-site/src/content/docs/known-issues.md`

**Interfaces:**
- Consumes: linked-only setup from `provider/setup_flow.py`, runtime configuration from `YandexYnisonProvider.get_config_entries`, and recovery behavior from `provider/ynison_client.py`.
- Produces: accurate setup, operation, and troubleshooting guidance.

- [ ] Update the landing page with prerequisites, purpose, linked-account model, one AudioSource per instance, and multi-instance usage.
- [ ] Replace the configuration page with setup/reconfigure, target-player selection, manual switching, output rate/depth, published name, and per-instance guidance.
- [ ] Replace known issues with linked-provider availability, credential rejection/refresh, automatic reconnect, unofficial protocol risk, regional restrictions, RADIO behavior, and player PCM compatibility.
- [ ] Install docs dependencies only if `docs-site/node_modules` is absent, then run:

```bash
npm ci --prefix docs-site
npm run build --prefix docs-site
../../.venv/bin/codespell docs-site/src/content/docs
git diff --check
```

Expected: Astro production build and spelling checks pass.

- [ ] Commit:

```bash
git add docs-site/src/content/docs/index.md docs-site/src/content/docs/configuration.md docs-site/src/content/docs/known-issues.md
git commit -m "docs: refresh setup and troubleshooting guide"
```

---

### Task 3: Replace Stale Planning Documents

**Files:**
- Modify: `ROADMAP.md`
- Modify: `IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: shipped architecture and known validation limitations.
- Produces: forward-looking roadmap and current implementation overview.

- [ ] Rewrite `ROADMAP.md` to retain dependency-baseline reproducibility, live integration coverage, provider decomposition, upstream signal-chain/queue UI, possible `ya-ynison` extraction, and potential multi-source support.
- [ ] Rewrite `IMPLEMENTATION_PLAN.md` as a shipped implementation overview covering setup, credentials, WebSocket lifecycle, AudioSource streaming, controls, queues, failures, and validation boundaries.
- [ ] Run:

```bash
../../.venv/bin/codespell ROADMAP.md IMPLEMENTATION_PLAN.md
rg -n "Current: v1\.2\.0|PluginSource currently|Phase 1: Ynison WebSocket Client" ROADMAP.md IMPLEMENTATION_PLAN.md
git diff --check
```

Expected: codespell succeeds and the focused search has no matches.

- [ ] Commit:

```bash
git add ROADMAP.md IMPLEMENTATION_PLAN.md
git commit -m "docs: replace historical plans with current roadmap"
```

---

### Task 4: Close Completed Feature Specifications

**Files:**
- Modify: `specs/done/0001-migrate-to-audiosource.md`
- Move: `specs/inprogress/0002-fix-claude-local-md-sample-rate.md` → `specs/done/0002-fix-claude-local-md-sample-rate.md`
- Move: `specs/inprogress/0003-ynison-send-delivery-signal.md` → `specs/done/0003-ynison-send-delivery-signal.md`
- Move: `specs/inprogress/0004-cache-borrow-mode-music-token.md` → `specs/done/0004-cache-borrow-mode-music-token.md`
- Move: `specs/inprogress/0005-provider-command-guard-cleanups.md` → `specs/done/0005-provider-command-guard-cleanups.md`
- Move: `specs/inprogress/0007-linked-yandex-auth-only.md` → `specs/done/0007-linked-yandex-auth-only.md`

**Interfaces:**
- Consumes: `CHANGELOG.md` evidence that specifications 0001-0007 shipped.
- Produces: empty WIP directory and consistent `status: done` frontmatter.

- [ ] Use `git mv` for 0002, 0003, 0004, 0005, and 0007.
- [ ] Change `status: inprogress` to `status: done` in 0001 and every moved file without rewriting historical content.
- [ ] Run:

```bash
test -z "$(find specs/inprogress -maxdepth 1 -name '*.md' -print -quit)"
! rg -L '^status: done$' specs/done/*.md
../../.venv/bin/codespell specs/done
git diff --check
```

Expected: no in-progress specs, every done spec has done frontmatter, and spelling/whitespace checks pass.

- [ ] Commit:

```bash
git add specs
git commit -m "docs: archive completed feature specifications"
```

---

### Task 5: Final Cross-Document Review and Verification

**Files:**
- Review: all changes from `origin/dev...HEAD`.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: verified clean documentation-sync branch.

- [ ] Build an evidence table during review mapping version/stage, AudioSource, linked auth, PCM floor, reconnect delays, and multi-instance claims to their repository-owned sources.
- [ ] Search maintained current-state documents:

```bash
rg -n "v2\.2\.9|Current: v1\.2\.0|PluginSource →|handoff \(experimental\)|24-bit / 48 kHz|несколько аккаунтов пока не поддерживаются|перезапустите Music Assistant" README.md CLAUDE.local.md ROADMAP.md IMPLEMENTATION_PLAN.md docs-site/src/content/docs
```

Expected: no matches; historical specs and changelog are excluded.

- [ ] Run focused gates:

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/ruff check provider tests
../../.venv/bin/ruff format --check provider tests
../../.venv/bin/codespell README.md CLAUDE.local.md ROADMAP.md IMPLEMENTATION_PLAN.md docs-site/src/content/docs specs/done
npm run build --prefix docs-site
../../.venv/bin/python scripts/check_method_order.py
git diff --check origin/dev...HEAD
```

Expected: every command exits zero.

- [ ] Attempt full gates:

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/mypy
```

Expected with the current lock: failures from pinned MA commit `9a3bb40e` lacking `setup_flow/get_setup_value` and the new stream-details contract. Report actual output if the baseline changes.

- [ ] Review scope:

```bash
git diff --stat origin/dev...HEAD
git diff --name-status origin/dev...HEAD
git status -sb
```

Confirm no production Python, dependency, manifest, version, or workflow file changed and no uncommitted changes remain.

- [ ] Commit review-only corrections with `docs: finalize current-codebase documentation` only when corrections were necessary; do not create an empty commit.
