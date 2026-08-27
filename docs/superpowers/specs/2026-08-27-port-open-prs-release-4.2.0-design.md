# Port Open Reverse-Sync PRs and Release 4.2.0

## Goal

Port the provider-facing changes from Music Assistant server PRs #5773, #5880,
#5914, #5944, and #6026 into the current standalone Yandex Ynison provider,
merge the generated wrapper sync from provider PR #149, and publish stable
provider version 4.2.0.

The result must use the current Music Assistant plugin and audio-source APIs
while preserving the provider's linked-Yandex-Music credential model, dynamic
format sessions, typed error boundaries, and stale-session protections.

## Non-goals

- Reintroducing QR login, manual Ynison tokens, or provider-owned credentials.
- Porting unrelated Music Assistant controller, frontend, or receiver-provider
  changes into this repository.
- Changing generated Ruff or mypy configuration by hand.
- Publishing directly to `music-assistant/server` or `trudenboy/ma-server`.
- Supporting `__auto__` as a valid target for new or reconfigured instances.

## Integration Strategy

Existing reverse-sync PRs remain the provenance boundary. Each branch is
updated from the latest `dev`, its generated conflict artifacts are replaced by
an adapted provider implementation, and it is merged only after its own review,
local gates, and GitHub checks pass.

The merge order is:

1. Provider PR #142 / upstream #5880: adopt `SourceControlValue` and update the
   locked Music Assistant/models baseline.
2. Provider PR #149: merge the generated lint and typing configuration after
   the source-control signature is compatible with it.
3. Provider PR #138 / upstream #5773: account Ynison playback against the
   linked Yandex Music provider's stream capacity.
4. Provider PR #143 / upstream #5914: migrate live-source ownership from a
   queue to the target player.
5. Provider PR #147 / upstream #5944: guard releases with provider, source, and
   playback-generation ownership.
6. Provider PR #151 / upstream #6026: require a concrete target player and
   derive the advertised name from that player.
7. A maintainer release PR: finish documentation and changelog consolidation,
   set `VERSION` to `4.2.0`, and trigger the stable pipeline.

This order intentionally ports #142 before the chronologically earlier #138.
The current lock lacks both `SourceControlValue` and the stream-slot API. A
single lock update to a Music Assistant commit containing all five upstream
changes makes #142 compatible first; #138 can then use the new capacity API
without making an intermediate branch impossible to type-check.

## Dependency Baseline

`pyproject.toml` continues to declare Music Assistant from the `dev` branch for
tests, while `uv.lock` records one reviewed commit at or after upstream #6026
and its matching `music-assistant-models` release. The selected checkout must
provide:

- `SourceControlValue` in the plugin model;
- player-owned `AudioSource` lifecycle callbacks;
- generation-aware source release;
- `MusicProvider.acquire_stream_slot()`;
- the core configuration migration for former `__auto__` instances.

The lock update must also produce a locally collectable test environment. The
pre-port baseline currently fails collection because the old frozen dependency
set imports `hass_client` without installing it; the updated lock is required
to remove that ambiguity before behavioral ports begin.

## Provider Behavior

### Source controls (#142)

`on_source_control` accepts the shared `SourceControlValue` union. Integer seek
positions remain non-negative seconds. Booleans are never treated as integers.
Unsupported repeat, shuffle, or absent values are ignored or rejected exactly
as the current Music Assistant plugin contract specifies; existing play,
pause, next, and previous behavior is unchanged.

### Linked-account stream capacity (#138)

Ynison does not own a music catalog stream. Before reading audio from a linked
Yandex Music `StreamDetails`, it resolves the exact linked music-provider
instance and acquires that instance's stream slot for the duration of the
upstream read. The slot is not held during setup, metadata lookup, preload, or
after the source generator exits.

The provider protocol exposes only the linked instance identity, availability,
quality, stream-details/audio methods, and capacity context required here.
Authentication, media-not-found, and invariant failures retain their existing
typed errors. Only expected transient stream and player-command failures enter
retry or best-effort paths.

### Player-owned source lifecycle (#143)

The active Ynison source is owned by the real target player instead of its
queue. Selection records player ownership and the current stream-session id.
External playback leaves the Music Assistant queue intact. Release and transfer
callbacks use the player identifier throughout; no path may refer to a removed
`queue_id` local.

The existing dynamic-format restart remains session-safe: a same-player format
restart replaces only its own generation and stale teardown cannot clear the
new playback.

### Generation-aware release (#147)

Every release carries enough ownership data to prove it still refers to the
active provider, source, player, and playback generation. A delayed cleanup
whose generation no longer matches becomes a no-op. Valid cleanup still resets
the provider's player/source state and cancels associated background work.

### Required player and derived name (#151)

Setup and reconfigure require one concrete Music Assistant player. The Auto
option and the standalone `publish_name` field are removed. The name published
to Yandex follows the selected player's current display name with the upstream
Ynison naming convention, and a relevant player-name update reloads or
refreshes the provider through the supported core mechanism.

`ym_instance` remains required. Setup still aborts with `missing_dependency`
when no Yandex Music provider exists, selects the sole compatible instance when
unambiguous, and clears legacy credential keys during reconfigure. No code or
strings from the obsolete upstream own-auth/QR branch are imported.

Existing configurations with `__auto__` rely on the matching Music Assistant
core migration and must prompt for a concrete player if no deterministic
mapping exists. The provider does not silently choose an arbitrary player.

## Configuration and Documentation

The implementation removes `CONF_PUBLISH_NAME` and `PLAYER_ID_AUTO` only after
tests pin migration and reconfigure behavior. `provider/strings.json`, setup
flow tests, README setup instructions, and `CLAUDE.local.md` configuration
ownership tables change together.

Generated `ruff.toml` and the generated sections of `pyproject.toml` come only
from provider PR #149. They are validated with the repository's config-sync
check and are not manually modified during feature work.

Each reverse-sync scaffold is rewritten into a complete specification and
moved from `specs/inprogress/` to `specs/done/` before merge. At no point does
the target branch contain more than one in-progress specification.

## Test Strategy

Behavior changes use red-green-refactor cycles on the relevant PR branch.
Tests cover at least:

- integer seek acceptance and boolean rejection for `SourceControlValue`;
- acquiring and releasing the exact linked provider's stream slot;
- slot release on normal completion, cancellation, and typed failure;
- player-owned selection and release without queue destruction;
- the former undefined-`queue_id` active-player path;
- stale generation cleanup leaving replacement playback intact;
- valid generation cleanup releasing the active source;
- setup with zero, one, and multiple linked Yandex Music instances;
- rejection of Auto and absence of a free-form published-name field;
- advertised-name derivation and player rename handling;
- preservation of dynamic format, linked credentials, radio, and typed-error
  regression suites.

Every PR must pass its focused tests, the full provider suite, Ruff check and
format check, mypy, `git diff --check`, and pre-commit. GitHub checks are read
again after the final pushed SHA. Marker scans cover Python, JSON, tests, specs,
and changelog files.

## Changelog and Versioning

The reverse-sync process lines appended to the historical 1.0.0 block are
removed. The first functional PR creates one future `4.2.0` Keep a Changelog
block; later PRs add user-facing bullets to the same block without editing old
releases. It contains only canonical headings and observable behavior.

`VERSION` remains `4.1.2` through the functional PRs. The final maintainer
release PR changes it to `4.2.0`, matching the changelog. A minor version is
used because setup loses Auto/free-form naming and source ownership semantics
change, even though core migration preserves supported existing instances.

## Merge, Release, and Verification

Before each merge, re-read the PR's changed-file list, reviews, conversations,
head SHA, mergeability, and checks. Merge only the reviewed head. After merge,
verify the commit on `dev` before updating the next branch.

After the release PR merges, the `pipeline.yml` push trigger must:

1. run the reusable provider gate;
2. create tag and GitHub Release `v4.2.0`;
3. sync the stable release to `upstream/yandex_ynison`;
4. sync the tested provider to `integration/dev`.

Completion requires checking the workflow conclusion, release assets, tag SHA,
release metadata, and both durable sync results. Command acceptance or a merge
button alone is not release evidence.

## Failure Handling and Recovery

- A failed local or GitHub gate stops the sequence; later dependent PRs are not
  merged.
- A new human review or changed branch head invalidates the preflight and is
  reviewed before continuing.
- Failed reverse-sync conflict resolution leaves the PR draft and
  `needs-human`; labels are removed only after marker scans and tests pass.
- A failed release workflow is diagnosed and retried only after confirming
  whether the tag, release, or sync already exists, avoiding duplicate
  publication.
- If 4.2.0 lands but has a provider regression, recovery is a forward patch
  release. Published tags and releases are not deleted or rewritten.
