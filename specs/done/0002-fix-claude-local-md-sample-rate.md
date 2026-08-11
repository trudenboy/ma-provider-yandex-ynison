---
id: "0002"
title: "Correct documented sample rate for superb/lossless PCM profile"
size: S
status: done
priority: P2
effort_minutes: 8
---

## Problem Statement

`CLAUDE.local.md` documents the no-hint auto-detection sample rate for
`superb` / `lossless` Yandex Music quality as **24-bit/44.1kHz**, but the
actual default emitted by the plugin is **24-bit/48kHz** (set in
`provider/streaming.py` and pinned by the green test
`test_superb_quality_uses_lossless_profile`). The CHANGELOG entry for
3.0.0 explicitly records this change ("Lossless PCM auto-mode default
sample rate is 48 kHz instead of 44.1 kHz when no source hint is
available"), but the per-repo CLAUDE doc was not updated alongside. An
operator triaging a "why is my DAC resampling?" report against the doc
will look in the wrong place and waste time.

## Solution Summary

Update `CLAUDE.local.md` so the no-hint auto-detection sentence matches
the code. Add a single doc-pinning test that reads the file and asserts
it documents the lossless profile derived from
`provider.streaming.PCM_LOSSLESS_PARAMS`, so future drift surfaces as a
red test rather than silent rot.

## Acceptance Criteria

1. The "Auto-detection (no hint)" sentence in `CLAUDE.local.md` reads
   `superb`/`lossless` → 24-bit/48kHz, else → 16-bit/44.1kHz.
2. A new `tests/test_docs.py::test_claude_local_md_documents_lossless_profile_correctly`
   reads `CLAUDE.local.md` via a path resolved relative to the test file
   (not CWD) and asserts the substring `"24-bit/48kHz"` is present.
3. The same test imports `PCM_LOSSLESS_PARAMS` from `provider.streaming`
   and derives the expected substring at runtime — so changing the
   constant alone will not silently re-introduce drift.
4. The test passes after the doc fix and is part of `uv run pytest`.
5. No code in `provider/` changes. `CHANGELOG.md` gains a single
   `### Documentation` bullet under a new patch-bump entry.

## Test Plan

- New unit test `tests/test_docs.py::test_claude_local_md_documents_lossless_profile_correctly`
  fails on `dev` (red) and passes on this branch (green) — diff visible in
  commit history.
- `uv run pytest tests/test_docs.py -v` — green.
- `uv run pytest` — full suite green.
- `pre-commit run --all-files` — clean.
- Manual: `grep "48kHz" CLAUDE.local.md` returns the auto-detection line.
