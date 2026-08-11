# Open PR Maintenance Design

## Goal

Bring the repository's open pull requests to a clear, maintainable state: land
the current upstream compatibility change in PR #127 and close PRs #120, #118,
#117, and #124 with precise explanations of why they should not be merged.

## Scope

The implementation changes only this provider repository and its pull
requests. It does not modify `trudenboy/ma-provider-tools`, recreate the
automated wrapper-sync PR, preserve changes from PR #117 in a replacement PR,
or change maintainer-owned `VERSION` content.

## PR #127 Completion

Work from the current head of `reverse-sync/yandex_ynison-pr5264` in an
isolated worktree. Preserve the upstream-compatible
`get_stream_details(item_id, media_type)` implementation and its regression
test updates.

Remove the generated placeholder reverse-sync specification. A separate
feature specification is not required because this is a compatibility port of
an already merged upstream interface change, not a new provider feature. State
that rationale explicitly in the PR body.

Replace the generated historical changelog bullet with one canonical entry at
the top of `CHANGELOG.md`. The entry must use an allowed Keep a Changelog
heading and describe the externally relevant compatibility change without
private symbols or internal file paths. Do not edit `VERSION`.

Run the full repository quality gate, review the final diff, push the updated
head to the existing PR branch, and wait for GitHub checks. Merge with squash
only after all required checks are successful and the PR remains conflict-free.
The user's request to implement this design is the explicit maintainer approval
required by `CLAUDE.md` for this merge.

## Obsolete PR Closure

After PR #127 is merged, re-read each target PR to ensure its state has not
changed, then leave one concise explanatory comment and close it:

- #120: the reverse-sync contains no setup-flow implementation, its tests
  fail against the removed authentication helper, and current `dev` already
  contains the replacement setup flow.
- #118: it removes the QR helper without removing all call sites, fails tests
  and typing, conflicts with `dev`, and current `dev` already contains the
  intended authentication cleanup.
- #117: it is a stale, conflicting test-only optimization; the current suite
  is already fast enough, and no replacement PR is requested.
- #124: its title claims a workflow-wrapper sync, but it changes no workflow
  files, downgrades the development authentication dependency inconsistently,
  and documents an authentication mode no longer supported by current `dev`.

Comments must discuss observable repository facts and must not claim the
external generator has been fixed.

## Safety and Failure Handling

Do not merge #127 if its head changes unexpectedly, required checks fail, or
GitHub reports a conflict. Stop and report the exact blocker instead. Closing
the obsolete PRs is independent of code mutation, but each closure must be
skipped if fresh inspection shows substantive new commits that invalidate the
recorded reason.

No human-review replies are needed: all five PRs currently have no reviews,
review threads, or conversation comments. If a human review appears before an
action, do not post an AI-authored reply in that thread; stop and hand it to the
maintainer as required by `CLAUDE.md`.

## Verification

For PR #127:

1. Run `pre-commit run --all-files` in the isolated worktree.
2. Confirm the diff contains only the compatibility change, its tests, the
   finalized changelog entry, PR-maintenance documentation, and removal of the
   generated placeholder specification.
3. Confirm GitHub CI is successful after the push.
4. Confirm the squash merge lands in `dev`.

For PR cleanup, query the repository after all closures and confirm that no
open PR remains from the original set. Any newly opened unrelated PR is outside
this design's scope.
