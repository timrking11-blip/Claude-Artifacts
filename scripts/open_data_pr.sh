#!/usr/bin/env bash
# Commit data to its own branch and land it through a pull request.
#
# The default branch takes changes only by PR with the `architecture` and
# `test` checks passing; no workflow bypasses that. A PR opened with the
# workflow's GITHUB_TOKEN does not trigger other workflows, so this script
# dispatches Python CI on the data branch itself (workflow_dispatch is the
# exception), and the checks land on the PR's head commit. The PR then waits
# for the owner: the repository is private on GitHub Free, with no rulesets or
# branch protection to gate a merge, so the owner merges data PRs by hand
# (decided 10 Oct 2026). This script never merges.
#
# Usage: scripts/open_data_pr.sh BRANCH "commit message" PATH...
#
# - Only PATH... may ride in the PR: anything else staged fails the run.
# - Re-runnable: BRANCH is fixed per workflow run (GITHUB_RUN_ID survives a
#   re-run), so a re-run finds what an earlier attempt pushed and resumes. An
#   open PR is reused, a merged one ends the run, a closed one fails it (the
#   owner closed it; a re-run never reopens it).
# - A green run means: the branch is pushed, the PR is open, and Python CI was
#   dispatched on the PR's exact head commit. It does not mean the data landed;
#   the PR awaits the owner's merge.
# - Python CI gets expected_sha = the pushed head, and fails unless the commit
#   it checked out is exactly that one.
# - PR_NOTE=<text>: appended to a new PR's body (the weekly sync names the
#   candidate the merge promotes).
#
# Needs GH_TOKEN, and permissions contents/pull-requests/actions: write.
# Writes `branch`, `pr`, `head` and `status` (awaiting_owner_merge | merged)
# to $GITHUB_OUTPUT.
set -euo pipefail

branch="$1"; message="$2"; shift 2
[ "$#" -gt 0 ] || { echo "::error::no data paths given"; exit 2; }
base="${BASE_BRANCH:-$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)}"
run_url="${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
attempt="${GITHUB_RUN_ATTEMPT:-1}"

output() { if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1=$2" >> "$GITHUB_OUTPUT"; fi; }

git config user.name "crm-sync[bot]"
git config user.email "crm-sync[bot]@users.noreply.github.com"
git add -- "$@"

# A data PR carries data only.
outside=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  ok=""
  for p in "$@"; do
    p="${p%/}"
    case "$f" in "$p"|"$p"/*) ok=1 ;; esac
  done
  [ -n "$ok" ] || outside="$outside $f"
done < <(git diff --cached --name-only)
if [ -n "$outside" ]; then
  echo "::error::staged files outside the data paths ($*):$outside"
  exit 3
fi

if git diff --cached --quiet; then
  echo "No data changes; no PR."
  exit 0
fi
git switch -C "$branch"
git commit -q -m "$message" -m "Workflow run $run_url (attempt $attempt)."

remote=$(git ls-remote --heads origin "refs/heads/$branch" | cut -f1)
if [ -z "$remote" ]; then
  git push -u origin "$branch"
else
  git fetch -q origin "refs/heads/$branch"
  if git diff --quiet FETCH_HEAD HEAD -- "$@"; then
    echo "Resuming: $branch already carries this data (an earlier attempt pushed it)."
    git reset -q --hard FETCH_HEAD
  else
    echo "Replacing $branch: this attempt's data differs from an earlier attempt's."
    git push --force-with-lease="refs/heads/$branch:$remote" origin "$branch"
  fi
fi
output branch "$branch"

pr=$(gh pr list --head "$branch" --state all --json number,state --jq '.[0] | "\(.number) \(.state)"')
case "$pr" in
  *" MERGED")
    echo "PR #${pr%% *} from $branch already merged; nothing left to do."
    output pr "${pr%% *}"
    output status merged
    exit 0 ;;
  *" CLOSED")
    echo "::error::PR #${pr%% *} from $branch was closed without merging; a re-run does not reopen it."
    exit 4 ;;
  *" OPEN")
    number="${pr%% *}"
    echo "Reusing open PR #$number." ;;
  *)
    body="Automated data commit from workflow run $run_url (attempt $attempt). Nothing merges it automatically: the owner merges it after \`architecture\` and \`test\` pass on its exact head commit."
    if [ -n "${PR_NOTE:-}" ]; then
      body="$body

$PR_NOTE"
    fi
    url=$(gh pr create --base "$base" --head "$branch" --title "$message" --body "$body")
    number="${url##*/}" ;;
esac
output pr "$number"

head=$(git rev-parse HEAD)
output head "$head"
if ! gh workflow run python-ci.yml --ref "$branch" -f expected_sha="$head"; then
  echo "::error::could not dispatch Python CI on $branch; PR #$number has no checks"
  exit 6
fi
# The dispatch runs on the branch's head when it starts, and CI itself fails
# unless that is $head; fail here too if anything moved the branch.
if [ "$(git ls-remote --heads origin "refs/heads/$branch" | cut -f1)" != "$head" ]; then
  echo "::error::$branch moved after the push; CI was dispatched on a head other than $head"
  exit 7
fi
output status awaiting_owner_merge
echo "PR #$number from $branch: awaiting owner merge (head $head; Python CI dispatched on it)."
