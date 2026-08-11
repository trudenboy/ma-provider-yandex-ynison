# Current-Codebase Documentation Sync Design

## Goal

Make every maintained documentation surface describe the stable 4.0.2 codebase:
the first-class `AudioSource` implementation, linked-only Yandex Music
authentication, the actual PCM normalization behavior, automatic Ynison
recovery, and the current multi-instance model.

## Sources of Truth

Documentation must derive factual claims from these repository-owned sources:

- `VERSION` for the provider version.
- `provider/manifest.json` for stage, domain, provider type, dependency, and
  multi-instance support.
- `provider/constants.py` and `provider/streaming.py` for configuration values,
  reconnect timing, and no-hint PCM profiles.
- `provider/setup_flow.py`, `provider/credential_source.py`, and
  `provider/provider.py` for setup, credential ownership, playback, queue, and
  stream behavior.
- `provider/ynison_client.py` for the transport, reconnect, echo-classification,
  and delivery semantics.
- `CHANGELOG.md` for historical version changes.

Documents must not introduce a second version or stage constant that requires
manual synchronization when a direct reference or a deliberately generic
statement is sufficient.

## Documentation Surfaces

### README

The README remains the concise English landing page. It will:

- identify the repository as stable without embedding the obsolete 2.2.9
  version;
- describe `AudioSource`, not the retired `PluginSource` contract;
- explain that every Ynison instance links to one configured `yandex_music`
  instance and never owns persistent credentials;
- describe the single stream mode and remove all current-tense handoff claims;
- document the 44.1 kHz no-hint lossless floor, per-track hint promotion, player
  rate snapping, and the normal passthrough path accurately;
- retain concise setup, development, protocol, and radio-queue guidance.

### Internal Architecture Guide

`CLAUDE.local.md` will become the detailed maintainer reference for the current
implementation. It will remove the handoff FSM, removed authentication keys,
and obsolete `PluginSource` terminology. It will document setup-owned versus
runtime configuration, session ownership, token refresh/cache boundaries,
stream format invariants, Ynison reconnect behavior, and queue replenishment.

### Documentation Site

The Russian docs site will contain an actionable user journey:

- prerequisites and linked-account setup;
- configuration and multi-instance behavior;
- playback and audio-quality behavior;
- troubleshooting that reflects automatic reconnect and linked credential
  refresh;
- genuine limitations: linked-provider dependency, unofficial Ynison protocol,
  single AudioSource per provider instance, external-service availability, and
  no end-to-end guarantee for every player transport.

Claims that multi-account is unsupported or that ordinary disconnects require a
manual restart will be removed.

### Roadmap and Implementation Overview

`ROADMAP.md` will contain only forward-looking work that remains relevant to
the current AudioSource architecture. Completed upstream-merge and old
PluginSource migration items will be removed.

`IMPLEMENTATION_PLAN.md` will be replaced by a current implementation overview.
It will explain the shipped architecture and validation boundaries rather than
present already completed phases as future work.

### Feature Specifications

Specifications 0001 through 0007 describe work already present in the stable
codebase. Their frontmatter will use `status: done`; files still under
`specs/inprogress/` will move to `specs/done/`. Historical discussion remains
intact unless it incorrectly claims to describe current behavior; historical
references to removed APIs are allowed when clearly framed as prior state.

## Validation Strategy

Human-facing prose will not gain new source-text pytest assertions. Such tests
would be brittle change detectors: they fail on intentional copy editing while
providing no evidence that a reader receives correct operational guidance.
Validation instead exercises the documentation artifacts and their structure:

1. Astro builds the docs site successfully.
2. Codespell, JSON/TOML parsers, and repository formatting checks pass.
3. Specification locations and frontmatter are inspected structurally after
   the moves.
4. Focused repository searches prove that known obsolete current-state claims
   were removed from maintained guides; historical specs and changelog remain
   outside that search.
5. A manual evidence table maps each important claim to its code-owned source
   before final review.

The existing `tests/test_docs.py` check remains part of the repository gate and
will pass against the corrected lossless-profile documentation, but this task
does not expand it with new prose assertions.

## Verification

Documentation verification will run independently of the known Music Assistant
lock mismatch and will include:

- the existing `tests/test_docs.py` check;
- an Astro production build;
- Ruff and formatting for `provider/` and `tests/`;
- codespell over the changed documentation;
- JSON/TOML parsing where applicable;
- repository searches for removed current-state terminology;
- `git diff --check` and a clean tracked worktree.

The full pytest and mypy gates will also be attempted and reported accurately.
They are currently expected to remain blocked because `uv.lock` pins Music
Assistant commit `9a3bb40e`, which predates `setup_flow`, `get_setup_value`, and
the shared `get_stream_details(item_id, media_type)` contract used by 4.0.2.
This documentation task will not modify dependency baselines or production
code.

## Non-Goals

- No production Python, dependency, manifest, version, or workflow changes.
- No new features or behavioral changes.
- No generated documentation framework.
- No claims that require live Ynison, Yandex Music, CDN, ffmpeg, or player
  integration testing when only unit/static evidence is available.
