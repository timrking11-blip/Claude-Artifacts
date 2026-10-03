#!/usr/bin/env bash
# Commit data to its own branch and land it through a pull request.
#
# The default branch takes changes only by PR with the `architecture` and
# `test` checks passing; no workflow bypasses that. A PR opened with the
# workflow's GITHUB_TOKEN does not trigger other workflows, so this script
# dispatches Python CI on the data branch itself (workflow_dispatch is the
# exception), and the checks land on the PR's head commit. Auto-merge then
# merges the PR once they pass.
#
# Usage: scripts/open_data_pr.sh BRANCH "commit message" PATH...
#
# - Only PATH... may ride in the PR: anything else staged fails the run.
# - Re-runnable: BRANCH is fixed per workflow run (GITHUB_RUN_ID survives a
#   re-run), so a re-run finds what an earlier attempt pushed and resumes. An
#   open PR is reused, a merged one ends the run, a closed one fails it (the
#   owner closed it; a re-run never reopens it).
# - Fails unless the PR is queued to land: a green run means auto-merge is on.
# - STACKED_ON=<branch>: this branch was cut from that data branch, so its PR
#   carries that PR's commits too; the body names the dependency.
#
# Needs GH_TOKEN, and permissions contents/pull-requests/actions: write.
# Writes `branch` and `pr` to $GITHUB_OUTPUT.
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
    exit 0 ;;
  *" CLOSED")
    echo "::error::PR #${pr%% *} from $branch was closed without merging; a re-run does not reopen it."
    exit 4 ;;
  *" OPEN")
    number="${pr%% *}"
    echo "Reusing open PR #$number." ;;
  *)
    body="Automated data commit from workflow run $run_url (attempt $attempt). Merges itself once \`architecture\` and \`test\` pass."
    if [ -n "${STACKED_ON:-}" ]; then
      dep=$(gh pr list --head "$STACKED_ON" --state all --json number --jq '.[0].number // empty')
      body="$body

Stacked on ${dep:+#$dep }(\`$STACKED_ON\`): this branch was cut from it, so this PR also carries its commits. Whichever merges first lands them; the other then merges only its own remainder."
    fi
    url=$(gh pr create --base "$base" --head "$branch" --title "$message" --body "$body")
    number="${url##*/}" ;;
esac
output pr "$number"

gh workflow run python-ci.yml --ref "$branch"
# Auto-merge waits for the checks the default branch's ruleset requires. A run
# that cannot queue its PR fails, so a green run always means "will land".
if ! gh pr merge "$number" --auto --merge; then
  echo "::error::auto-merge could not be enabled on PR #$number; the data will not land until it is merged"
  exit 5
fi
echo "PR #$number from $branch is queued to merge once its checks pass."
