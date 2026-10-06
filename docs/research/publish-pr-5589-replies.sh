#!/usr/bin/env bash
# Publish reviewed replies to music-assistant/server#5589 review threads.
#
# Usage:
#   publish-pr-5589-replies.sh [replies.json]          # dry run (default)
#   publish-pr-5589-replies.sh [replies.json] --post   # publish approved replies
#
# Run this yourself after you have reviewed every reply. Only entries with
# "approved": true are posted. Replies to human reviewers must be written in
# your own words (AI policy rule 3). Bot threads are skipped as soon as a
# human has joined them.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
file="${here}/pr-5589-replies-v4.3.7.json"
post=false
for arg in "$@"; do
    case "$arg" in
        --post) post=true ;;
        -h | --help) sed -n '2,11p' "$0"; exit 0 ;;
        *) file="$arg" ;;
    esac
done

for tool in gh jq; do
    command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }
done

repo="$(jq -r .repo "$file")"
pr="$(jq -r .pr "$file")"
release="$(jq -r .release "$file")"
owner="${repo%/*}"
name="${repo#*/}"
marker_prefix="ynison-review-reply"

echo "== Preflight: ${repo}#${pr}, expected release ${release}"
pr_json="$(gh api "repos/${repo}/pulls/${pr}")"
state="$(jq -r .state <<<"$pr_json")"
head_sha="$(jq -r .head.sha <<<"$pr_json")"
title="$(jq -r .title <<<"$pr_json")"
author="$(jq -r .user.login <<<"$pr_json")"
[[ "$state" == "open" ]] || { echo "PR is ${state}; aborting" >&2; exit 1; }

version="$(gh api "repos/${repo}/contents/music_assistant/providers/yandex_ynison/VERSION?ref=${head_sha}" \
    --jq .content | base64 -d | tr -d '[:space:]')"
problems=0
if [[ "$version" != "$release" ]]; then
    echo "  VERSION at ${head_sha:0:9} is ${version}, expected ${release}" >&2
    problems=1
fi
if [[ "$title" != *"$release"* ]]; then
    echo "  PR title does not mention ${release}: ${title}" >&2
    problems=1
fi
if ((problems)) && $post; then
    echo "Sync the release and update the PR title/body before posting." >&2
    exit 1
fi

# Every review thread with its comments, keyed later by the root comment id.
threads="$(gh api graphql --paginate -F owner="$owner" -F name="$name" -F pr="$pr" -f query='
query($owner: String!, $name: String!, $pr: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved
          comments(first: 100) {
            nodes { databaseId body author { login __typename } }
          }
        }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes[]' | jq -s .)"

posted=0 skipped=0
while IFS= read -r entry; do
    id="$(jq -r .comment_id <<<"$entry")"
    kind="$(jq -r .kind <<<"$entry")"
    approved="$(jq -r '.approved // false' <<<"$entry")"
    resolve="$(jq -r '.resolve // false' <<<"$entry")"
    body="$(jq -r .body <<<"$entry")"
    marker="<!-- ${marker_prefix}:r${id}:v${release} -->"
    thread="$(jq --argjson id "$id" \
        'map(select(.comments.nodes[0].databaseId == $id)) | first // empty' <<<"$threads")"

    echo
    echo "== r${id} (${kind})"
    if [[ -z "$thread" ]]; then
        echo "  SKIP: thread not found"; skipped=$((skipped + 1)); continue
    fi
    if [[ "$(jq -r .isResolved <<<"$thread")" == "true" ]]; then
        echo "  SKIP: thread already resolved"; skipped=$((skipped + 1)); continue
    fi
    if jq -e --arg m "$marker" 'any(.comments.nodes[]; .body | contains($m))' <<<"$thread" >/dev/null; then
        echo "  SKIP: reply for ${release} already posted"; skipped=$((skipped + 1)); continue
    fi
    if [[ "$kind" == "bot" ]] &&
        jq -e --arg me "$author" \
            'any(.comments.nodes[1:][]; .author.__typename == "User" and .author.login != $me)' \
            <<<"$thread" >/dev/null; then
        echo "  SKIP: a human joined this bot thread; write this reply yourself (rule 3)"
        skipped=$((skipped + 1)); continue
    fi
    if [[ "$approved" != "true" ]]; then
        echo "  SKIP: not approved"; skipped=$((skipped + 1)); continue
    fi

    printf '%s\n' "$body" | sed 's/^/  | /'
    if ! $post; then
        echo "  DRY RUN: would reply (resolve=${resolve})"; continue
    fi
    gh api "repos/${repo}/pulls/${pr}/comments/${id}/replies" \
        -f body="$(printf '%s\n\n%s' "$body" "$marker")" --jq .html_url
    posted=$((posted + 1))
    if [[ "$kind" == "bot" && "$resolve" == "true" ]]; then
        gh api graphql -f id="$(jq -r .id <<<"$thread")" -f query='
mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' \
            --jq '"  resolved: \(.data.resolveReviewThread.thread.isResolved)"'
    fi
done < <(jq -c '.replies[]' "$file")

echo
echo "== Done: posted=${posted} skipped=${skipped} (post mode: ${post})"
echo "Human reviewer threads are left open for the reviewer to resolve."
