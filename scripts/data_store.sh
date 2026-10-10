#!/usr/bin/env bash
# The data branch: where data/master and data/runs live since they left the
# committed tree (#26, for advisor sharing; the owner chose this branch on
# 10 Oct 2026 over a separate repo or re-tracking them).
#
# `data/store` is an orphan branch with the same paths as the working tree
# (data/master/contacts.json, data/runs/<run>/...). Nothing here touches the
# index or the current branch: restore writes files into the working tree,
# where .gitignore keeps them out of every commit; save commits through a
# temporary worktree and pushes straight to the data branch, which holds data,
# never code.
#
# Usage:
#   scripts/data_store.sh restore PATH...        PATH as on the data branch, e.g. data/master
#   scripts/data_store.sh save "message" PATH... snapshot each PATH from here onto the branch
#
# restore fails when the branch or a PATH is missing: a sync that silently
# started from an empty master would count every contact as new.
# save replaces each PATH on the branch with this checkout's copy (paths it is
# not given are kept), commits only if something changed, and retries on a
# concurrent push by re-applying the same snapshot onto the new head.
set -euo pipefail

BRANCH="${DATA_STORE_BRANCH:-data/store}"
REMOTE="${DATA_STORE_REMOTE:-origin}"

fetch() {
  git fetch -q "$REMOTE" "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH" 2>/dev/null \
    || { echo "::error::$REMOTE has no branch $BRANCH"; exit 4; }
}

cmd="${1:-}"; shift || true
case "$cmd" in
  restore)
    [ "$#" -gt 0 ] || { echo "::error::restore needs at least one path"; exit 2; }
    fetch
    for p in "$@"; do
      p="${p%/}"
      if ! git cat-file -e "$REMOTE/$BRANCH:$p" 2>/dev/null; then
        echo "::error::$p is not on $BRANCH"; exit 3
      fi
      rm -rf -- "$p"
      git archive "$REMOTE/$BRANCH" -- "$p" | tar -x
      echo "restored $p from $BRANCH ($(git rev-parse --short "$REMOTE/$BRANCH"))"
    done ;;
  save)
    message="${1:-}"; shift || true
    [ -n "$message" ] && [ "$#" -gt 0 ] || { echo "::error::save needs a message and at least one path"; exit 2; }
    here="$(pwd)"
    tmp="$(mktemp -d)"
    trap 'git worktree remove --force "$tmp" >/dev/null 2>&1 || rm -rf "$tmp"' EXIT
    for attempt in 1 2 3; do
      fetch
      git worktree remove --force "$tmp" >/dev/null 2>&1 || true
      git worktree add -q --detach "$tmp" "$REMOTE/$BRANCH"
      for p in "$@"; do
        p="${p%/}"
        [ -e "$here/$p" ] || { echo "::error::$p does not exist here; nothing to save"; exit 3; }
        rm -rf -- "${tmp:?}/$p"
        mkdir -p "$(dirname "$tmp/$p")"
        cp -a "$here/$p" "$tmp/$p"
      done
      git -C "$tmp" add -A -- "$@"
      if git -C "$tmp" diff --cached --quiet; then
        echo "$BRANCH already holds this data; nothing to save."
        exit 0
      fi
      git -C "$tmp" -c user.name="${GIT_AUTHOR_NAME:-crm-sync[bot]}" \
        -c user.email="${GIT_AUTHOR_EMAIL:-crm-sync[bot]@users.noreply.github.com}" \
        commit -q -m "$message"
      if git -C "$tmp" push -q "$REMOTE" "HEAD:refs/heads/$BRANCH"; then
        echo "saved $* to $BRANCH ($(git -C "$tmp" rev-parse --short HEAD))"
        exit 0
      fi
      echo "push to $BRANCH was rejected (attempt $attempt); re-applying onto the new head"
    done
    echo "::error::could not save to $BRANCH after 3 attempts"; exit 5 ;;
  *)
    echo "usage: $0 restore PATH... | save MESSAGE PATH..." >&2; exit 2 ;;
esac
