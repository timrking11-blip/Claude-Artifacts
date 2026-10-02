#!/usr/bin/env bash
# Commit staged data to its own branch and land it through a pull request.
#
# The default branch takes changes only by PR with the `architecture` and
# `test` checks passing; no workflow bypasses that. A PR opened with the
# workflow's GITHUB_TOKEN does not trigger other workflows, so this script
# dispatches Python CI on the data branch itself (workflow_dispatch is the
# exception), and the checks land on the PR's head commit. Auto-merge then
# merges the PR once they pass.
#
# Usage: scripts/open_data_pr.sh BRANCH "commit message" PATH...
# Needs: GH_TOKEN, and permissions contents/pull-requests/actions: write.
# Prints the branch name to $GITHUB_OUTPUT as `branch` when a PR was opened.
set -euo pipefail

branch="$1"; message="$2"; shift 2
base="${BASE_BRANCH:-$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)}"

git config user.name "crm-sync[bot]"
git config user.email "crm-sync[bot]@users.noreply.github.com"
git add "$@"
if git diff --cached --quiet; then
  echo "No data changes; no PR."
  exit 0
fi
git switch -c "$branch"
git commit -m "$message"
git push -u origin "$branch"

gh pr create --base "$base" --head "$branch" --title "$message" \
  --body "Automated data commit from workflow run ${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}. Merges itself once \`architecture\` and \`test\` pass."
gh workflow run python-ci.yml --ref "$branch"
# Auto-merge waits for the checks the default branch's ruleset requires. If it
# cannot be enabled, the PR stays open for the owner to merge.
gh pr merge "$branch" --auto --merge || echo "::warning::auto-merge not enabled; merge the data PR by hand"

[ -n "${GITHUB_OUTPUT:-}" ] && echo "branch=$branch" >> "$GITHUB_OUTPUT"
echo "Opened data PR from $branch"
