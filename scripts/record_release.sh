#!/usr/bin/env bash
# Append a line for this data release to RELEASES.md on the data-log branch, through the
# GitHub API. The commit counts as repository activity, which keeps the monthly schedule from
# being switched off after 60 quiet days, without pushing to the protected main branch.
# Needs: GH_TOKEN (contents: write), GITHUB_REPOSITORY, RELEASE (YYYY-MM), PARTIAL (true/false).
set -euo pipefail

branch="data-log"
file="RELEASES.md"
repo="repos/$GITHUB_REPOSITORY"

if ! gh api "$repo/git/ref/heads/$branch" > /dev/null 2>&1; then
  # A branch with no history of its own: a root commit holding just the log file.
  tree=$(gh api -X POST "$repo/git/trees" -f "tree[][path]=$file" -f "tree[][mode]=100644" \
    -f "tree[][type]=blob" -f "tree[][content]=# Data releases" --jq .sha)
  commit=$(gh api -X POST "$repo/git/commits" -f message="data: start the release log" \
    -f tree="$tree" --jq .sha)
  gh api -X POST "$repo/git/refs" -f ref="refs/heads/$branch" -f sha="$commit" > /dev/null
fi

existing=$(gh api "$repo/contents/$file?ref=$branch")
old_sha=$(jq -r .sha <<< "$existing")
body=$(jq -r .content <<< "$existing" | base64 -d) # $(...) drops trailing newlines

suffix=""
[ "$PARTIAL" = "true" ] && suffix="-partial (prerelease)"
line="- data-$RELEASE$suffix published $(date -u +%Y-%m-%dT%H:%MZ)"
case "$body" in
  *-*) new="$body"$'\n'"$line"$'\n' ;;           # already has entries
  *) new="$body"$'\n\n'"$line"$'\n' ;;           # just the heading
esac

gh api -X PUT "$repo/contents/$file" -f message="data: record release data-$RELEASE$suffix" \
  -f branch="$branch" -f sha="$old_sha" -f content="$(printf '%s' "$new" | base64 | tr -d '\n')" \
  > /dev/null
echo "Recorded data-$RELEASE$suffix on $branch"
