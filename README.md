# data/store

The data branch. It holds what left the committed tree in #26 (9 Oct 2026):

- `data/master/` — the merged contact master the weekly sync reads and writes
  (`scripts/data_store.sh restore data/master`, then `save` after the merge).
- `data/runs/` — composition run outputs.

It has no code and shares no history with the default branch. Paths mirror the
working tree, so `scripts/data_store.sh restore <path>` drops files where the
scripts expect them; `.gitignore` on the default branch keeps them out of every
code commit. Seeded from commit 1e8104b, the last commit before #26: master of
28 Sep 2026 14:46:53 UTC, 77 contacts.
