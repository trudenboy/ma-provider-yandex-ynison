# Current-Codebase Documentation Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every maintained document describe the stable 4.0.2 AudioSource implementation and prevent the same factual drift from returning.

**Architecture:** Treat `VERSION`, `provider/manifest.json`, and provider constants/implementation as the factual sources of truth. Add durable repository-file assertions before changing prose, update each documentation surface in focused commits, and keep historical specifications intact while marking completed work as done.

**Tech Stack:** Markdown, Python 3.14, pytest, Ruff, codespell, Git.

## Global Constraints

- Do not modify production Python, dependencies, `VERSION`, the manifest, workflows, or runtime behavior.
- Describe only the shipped `AudioSource` stream path; do not advertise removed handoff or own-credential modes.
- Every Ynison instance links to exactly one configured `yandex_music` provider.
- The lossless no-hint floor is 24-bit/44.1 kHz; real stream hints may lift it and player capabilities may snap it down.
- Ordinary Ynison disconnects recover automatically with 5/10/30/60-second saturated backoff and jitter.
- Preserve historical explanations inside completed specs when they are clearly framed as prior state.
- Report the known `uv.lock`/Music Assistant API mismatch accurately; do not fix it in this documentation task.

---

### Task 1: Pin and Update the Core English Documentation

**Files:**
- Modify: `tests/test_docs.py`
- Modify: `README.md`
- Modify: `CLAUDE.local.md`

**Interfaces:**
- Consumes: `VERSION`, `provider/manifest.json`, `provider.streaming.PCM_LOSSLESS_PARAMS`.
- Produces: current README and maintainer architecture guide with regression assertions.

- [ ] **Step 1: Add failing current-state assertions**

Add imports for `json` and `pytest`, then add:

```python
@pytest.mark.parametrize("filename", ["README.md", "CLAUDE.local.md"])
def test_core_docs_describe_current_audio_source(filename: str) -> None:
    text = (_REPO_ROOT / filename).read_text(encoding="utf-8")
    assert "PluginSource →" not in text
    assert "handoff (experimental)" not in text
    assert "own credentials" not in text.lower()


def test_readme_stage_matches_manifest() -> None:
    manifest = json.loads(
        (_REPO_ROOT / "provider/manifest.json").read_text(encoding="utf-8")
    )
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"**{manifest['stage'].title()}**" in readme
    assert "v2.2.9" not in readme


@pytest.mark.parametrize("filename", ["README.md", "CLAUDE.local.md"])
def test_core_docs_document_lossless_floor(filename: str) -> None:
    bit_depth = PCM_LOSSLESS_PARAMS["bit_depth"]
    sample_rate_khz = f"{PCM_LOSSLESS_PARAMS['sample_rate'] / 1000:g}"
    text = (_REPO_ROOT / filename).read_text(encoding="utf-8")
    assert f"{bit_depth}-bit/{sample_rate_khz}kHz" in text
```

- [ ] **Step 2: Run the assertions and verify RED**

Run: `../../.venv/bin/python -m pytest -q tests/test_docs.py`

Expected: failures identify the obsolete beta/version, PluginSource/handoff/own-credentials text, and README 48 kHz lossless claim.

- [ ] **Step 3: Rewrite `README.md` as the concise project landing page**

Keep the generated badge/header block intact. Cover stable status, AudioSource architecture, linked credentials, setup/reconfigure, 44.1 kHz lossless floor, hint promotion, player-rate snapping, automatic reconnect, echo suppression, strict command delivery, RADIO replenishment, and accurate development commands.

- [ ] **Step 4: Rewrite `CLAUDE.local.md` as the current maintainer guide**

Use sections for project overview, architecture, invariants, modules, setup/runtime configuration, credential lifecycle, streaming/session ownership, Ynison recovery, radio queues, and verification. Remove the handoff FSM, old auth actions, `PluginSource`, and personal absolute paths.

- [ ] **Step 5: Run the assertions and verify GREEN**

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/ruff check tests/test_docs.py
../../.venv/bin/ruff format --check tests/test_docs.py
```

Expected: all documentation tests pass and static checks are clean.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.local.md tests/test_docs.py
git commit -m "docs: align core guides with AudioSource implementation"
```

---

### Task 2: Replace the User-Facing Documentation Site Content

**Files:**
- Modify: `tests/test_docs.py`
- Modify: `docs-site/src/content/docs/index.md`
- Modify: `docs-site/src/content/docs/configuration.md`
- Modify: `docs-site/src/content/docs/known-issues.md`

**Interfaces:**
- Consumes: linked-only setup from `provider/setup_flow.py` and reconnect behavior from `provider/ynison_client.py`.
- Produces: accurate Russian setup, operation, and troubleshooting documentation.

- [ ] **Step 1: Add a failing docs-site assertion**

```python
def test_docs_site_describes_supported_multi_instance_recovery() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (_REPO_ROOT / "docs-site/src/content/docs").glob("*.md")
    ).lower()
    assert "несколько аккаунтов пока не поддерживаются" not in docs
    assert "перезапустите music assistant" not in docs
    assert "связанный" in docs
    assert "автоматически" in docs
```

- [ ] **Step 2: Run it and verify RED**

Run: `../../.venv/bin/python -m pytest -q tests/test_docs.py::test_docs_site_describes_supported_multi_instance_recovery`

Expected: failure on obsolete multi-account and manual-restart guidance.

- [ ] **Step 3: Update `index.md`**

Explain the plugin purpose, required configured Yandex Music provider, one linked account and one AudioSource per instance, and multiple instances for multiple accounts/players.

- [ ] **Step 4: Replace `configuration.md`**

Document prerequisites, setup/reconfigure, linked account selection, target-player auto-selection, manual switching, output rate/depth, published name, and per-instance behavior.

- [ ] **Step 5: Replace `known-issues.md`**

Cover linked-provider availability, token rejection/refresh, automatic reconnect, unofficial protocol risk, regional/subscription restrictions, RADIO replenishment, and player-specific PCM compatibility. Do not prescribe deletion or restart for ordinary disconnects.

- [ ] **Step 6: Run and verify GREEN**

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/codespell docs-site/src/content/docs tests/test_docs.py
```

Expected: documentation tests and spelling checks pass.

- [ ] **Step 7: Commit**

```bash
git add docs-site/src/content/docs/index.md docs-site/src/content/docs/configuration.md docs-site/src/content/docs/known-issues.md tests/test_docs.py
git commit -m "docs: refresh setup and troubleshooting guide"
```

---

### Task 3: Replace Stale Planning Documents

**Files:**
- Modify: `tests/test_docs.py`
- Modify: `ROADMAP.md`
- Modify: `IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: shipped architecture and remaining limitations established in Tasks 1-2.
- Produces: forward-looking roadmap and current implementation overview.

- [ ] **Step 1: Add a failing stale-planning assertion**

```python
@pytest.mark.parametrize("filename", ["ROADMAP.md", "IMPLEMENTATION_PLAN.md"])
def test_planning_docs_do_not_present_retired_contract_as_current(filename: str) -> None:
    text = (_REPO_ROOT / filename).read_text(encoding="utf-8")
    assert "Current: v1.2.0" not in text
    assert "PluginSource currently" not in text
    assert "Phase 1: Ynison WebSocket Client" not in text
```

- [ ] **Step 2: Run it and verify RED**

Run: `../../.venv/bin/python -m pytest -q tests/test_docs.py::test_planning_docs_do_not_present_retired_contract_as_current`

Expected: failures identify the old v1.2 roadmap and phase framing.

- [ ] **Step 3: Rewrite `ROADMAP.md`**

Keep dependency-baseline reproducibility, integration coverage, provider-class decomposition, signal-chain UI, external-source queue UI, possible `ya-ynison` extraction, and potential multi-source support.

- [ ] **Step 4: Rewrite `IMPLEMENTATION_PLAN.md` as an implementation overview**

Describe shipped boundaries, initialization, credentials, WebSocket lifecycle, AudioSource streaming, control sync, queue replenishment, failure handling, and validation limits.

- [ ] **Step 5: Run and verify GREEN**

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/codespell ROADMAP.md IMPLEMENTATION_PLAN.md tests/test_docs.py
```

Expected: documentation tests and spelling checks pass.

- [ ] **Step 6: Commit**

```bash
git add ROADMAP.md IMPLEMENTATION_PLAN.md tests/test_docs.py
git commit -m "docs: replace historical plans with current roadmap"
```

---

### Task 4: Close Completed Feature Specifications

**Files:**
- Modify: `tests/test_docs.py`
- Modify: `specs/done/0001-migrate-to-audiosource.md`
- Move: `specs/inprogress/0002-fix-claude-local-md-sample-rate.md` → `specs/done/0002-fix-claude-local-md-sample-rate.md`
- Move: `specs/inprogress/0003-ynison-send-delivery-signal.md` → `specs/done/0003-ynison-send-delivery-signal.md`
- Move: `specs/inprogress/0004-cache-borrow-mode-music-token.md` → `specs/done/0004-cache-borrow-mode-music-token.md`
- Move: `specs/inprogress/0005-provider-command-guard-cleanups.md` → `specs/done/0005-provider-command-guard-cleanups.md`
- Move: `specs/inprogress/0007-linked-yandex-auth-only.md` → `specs/done/0007-linked-yandex-auth-only.md`

**Interfaces:**
- Consumes: `CHANGELOG.md` evidence that specifications 0001-0007 shipped.
- Produces: an empty WIP directory and consistent `status: done` frontmatter.

- [ ] **Step 1: Add a failing spec-state assertion**

```python
def test_completed_spec_locations_and_frontmatter_are_consistent() -> None:
    inprogress = list((_REPO_ROOT / "specs/inprogress").glob("*.md"))
    assert inprogress == []
    for path in (_REPO_ROOT / "specs/done").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "status: done" in text, f"{path} is under done without done status"
```

- [ ] **Step 2: Run it and verify RED**

Run: `../../.venv/bin/python -m pytest -q tests/test_docs.py::test_completed_spec_locations_and_frontmatter_are_consistent`

Expected: failure lists five in-progress files and the incorrect 0001 frontmatter.

- [ ] **Step 3: Move completed specifications**

Use `git mv` for 0002, 0003, 0004, 0005, and 0007, preserving contents and history.

- [ ] **Step 4: Normalize frontmatter**

Change `status: inprogress` to `status: done` in 0001 and every moved file. Do not rewrite historical problem statements or acceptance criteria.

- [ ] **Step 5: Run and verify GREEN**

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/codespell specs/done tests/test_docs.py
```

Expected: documentation tests and spelling checks pass.

- [ ] **Step 6: Commit**

```bash
git add specs tests/test_docs.py
git commit -m "docs: archive completed feature specifications"
```

---

### Task 5: Final Cross-Document Review and Verification

**Files:**
- Review: all changes from `origin/dev...HEAD`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: final review evidence and a clean branch.

- [ ] **Step 1: Search maintained docs for stale claims**

```bash
rg -n "v2\.2\.9|Current: v1\.2\.0|PluginSource →|handoff \(experimental\)|24-bit / 48 kHz|несколько аккаунтов пока не поддерживаются|перезапустите Music Assistant" README.md CLAUDE.local.md ROADMAP.md IMPLEMENTATION_PLAN.md docs-site/src/content/docs
```

Expected: no matches. Historical specs and changelog are intentionally excluded.

- [ ] **Step 2: Run documentation/static gates**

```bash
../../.venv/bin/python -m pytest -q tests/test_docs.py
../../.venv/bin/ruff check provider tests
../../.venv/bin/ruff format --check provider tests
../../.venv/bin/codespell README.md CLAUDE.local.md ROADMAP.md IMPLEMENTATION_PLAN.md docs-site/src/content/docs specs/done tests/test_docs.py
../../.venv/bin/python scripts/check_method_order.py
git diff --check origin/dev...HEAD
```

Expected: every command exits zero.

- [ ] **Step 3: Attempt full repository gates**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/mypy
```

Expected with the current lock: pytest/provider construction fails because pinned MA commit `9a3bb40e` lacks `setup_flow/get_setup_value`; mypy reports the same API mismatch and old stream-details override. If the baseline changes, report actual successful results.

- [ ] **Step 4: Review scope and tree**

```bash
git diff --stat origin/dev...HEAD
git diff --name-status origin/dev...HEAD
git status -sb
```

Confirm no production Python, dependency, manifest, version, or workflow file changed, and no uncommitted changes remain.

- [ ] **Step 5: Commit review corrections only when needed**

If review requires corrections, stage only documentation/test files and commit:

```bash
git commit -m "docs: finalize current-codebase documentation"
```

Do not create an empty commit.
