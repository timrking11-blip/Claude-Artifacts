"""scripts/data_store.sh: data/master and data/runs live on the data/store branch.

Each test runs the real script against a local bare remote. It pins what the
sync and the routines rely on: restore brings the branch's files into the
working tree without staging anything, a missing branch or path fails loudly
(an empty master would count every contact as new), and save commits only
the paths it is given, only when they changed, and survives a concurrent push.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "data_store.sh"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


def store(cwd, *args):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(remote), str(seed))
    (seed / ".gitignore").write_text("data/master/\ndata/runs/\n")
    (seed / "code.py").write_text("x = 1\n")
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "code")
    git(seed, "push", "-q", "origin", "HEAD:main")
    # the data branch: an orphan with the same paths as the working tree
    git(seed, "checkout", "-q", "--orphan", "data/store")
    git(seed, "rm", "-rq", "--cached", ".")
    for f in (".gitignore", "code.py"):
        (seed / f).unlink()
    (seed / "data" / "master").mkdir(parents=True)
    (seed / "data" / "master" / "contacts.json").write_text('[{"id": 1}]\n')
    (seed / "data" / "runs" / "run_a").mkdir(parents=True)
    (seed / "data" / "runs" / "run_a" / "summary.json").write_text("{}\n")
    git(seed, "add", "-f", "data")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", "origin", "HEAD:refs/heads/data/store")
    return tmp_path, remote


def checkout(tmp_path, remote, name):
    work = tmp_path / name
    git(tmp_path, "clone", "-q", "-b", "main", str(remote), str(work))
    return work


def on_branch(tmp_path, remote, path):
    return git(tmp_path, "--git-dir", str(remote), "show", f"data/store:{path}")


def test_the_script_parses():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_restore_writes_the_branch_files_and_stages_nothing(repo):
    tmp, remote = repo
    work = checkout(tmp, remote, "w")
    r = store(work, "restore", "data/master")
    assert r.returncode == 0, r.stderr + r.stdout
    assert (work / "data" / "master" / "contacts.json").read_text() == '[{"id": 1}]\n'
    assert git(work, "status", "--porcelain") == ""  # ignored, never staged
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_restore_replaces_a_stale_local_copy(repo):
    tmp, remote = repo
    work = checkout(tmp, remote, "w")
    (work / "data" / "master").mkdir(parents=True)
    (work / "data" / "master" / "old.json").write_text("stale\n")
    assert store(work, "restore", "data/master").returncode == 0
    assert sorted(p.name for p in (work / "data" / "master").iterdir()) == ["contacts.json"]


def test_restore_fails_on_a_missing_path_or_branch(repo, monkeypatch):
    tmp, remote = repo
    work = checkout(tmp, remote, "w")
    r = store(work, "restore", "data/nothing")
    assert r.returncode == 3 and "not on data/store" in r.stdout + r.stderr
    monkeypatch.setenv("DATA_STORE_BRANCH", "data/missing")
    r = store(work, "restore", "data/master")
    assert r.returncode == 4 and "has no branch" in r.stdout + r.stderr


def test_save_commits_only_the_given_paths_and_keeps_the_rest(repo):
    tmp, remote = repo
    work = checkout(tmp, remote, "w")
    assert store(work, "restore", "data/master").returncode == 0
    (work / "data" / "master" / "contacts.json").write_text('[{"id": 1}, {"id": 2}]\n')
    (work / "code.py").write_text("x = 2\n")  # code never rides to the data branch
    r = store(work, "save", "data: weekly sync", "data/master")
    assert r.returncode == 0, r.stderr + r.stdout
    assert on_branch(tmp, remote, "data/master/contacts.json") == '[{"id": 1}, {"id": 2}]'
    assert on_branch(tmp, remote, "data/runs/run_a/summary.json") == "{}"
    files = git(tmp, "--git-dir", str(remote), "ls-tree", "-r", "--name-only", "data/store").split()
    assert "code.py" not in files
    # the checkout is left as it was: nothing staged, the code edit still unstaged
    assert git(work, "diff", "--cached", "--name-only") == ""
    assert git(work, "diff", "--name-only") == "code.py"
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_save_with_nothing_changed_makes_no_commit(repo):
    tmp, remote = repo
    work = checkout(tmp, remote, "w")
    assert store(work, "restore", "data/master").returncode == 0
    before = git(tmp, "--git-dir", str(remote), "rev-parse", "data/store")
    r = store(work, "save", "data: weekly sync", "data/master")
    assert r.returncode == 0 and "nothing to save" in r.stdout
    assert git(tmp, "--git-dir", str(remote), "rev-parse", "data/store") == before


def test_save_lands_on_top_of_a_concurrent_push(repo):
    tmp, remote = repo
    sync = checkout(tmp, remote, "sync")
    assert store(sync, "restore", "data/master").returncode == 0
    # a composition run saves a new run while the sync is working
    comp = checkout(tmp, remote, "comp")
    (comp / "data" / "runs" / "run_b").mkdir(parents=True)
    (comp / "data" / "runs" / "run_b" / "summary.json").write_text('{"b": 1}\n')
    assert store(comp, "save", "data: run_b", "data/runs/run_b").returncode == 0
    (sync / "data" / "master" / "contacts.json").write_text('[{"id": 3}]\n')
    r = store(sync, "save", "data: weekly sync", "data/master")
    assert r.returncode == 0, r.stderr + r.stdout
    assert on_branch(tmp, remote, "data/master/contacts.json") == '[{"id": 3}]'
    assert on_branch(tmp, remote, "data/runs/run_b/summary.json") == '{"b": 1}'


def test_save_refuses_a_path_that_does_not_exist_here(repo):
    tmp, remote = repo
    work = checkout(tmp, remote, "w")
    r = store(work, "save", "data: weekly sync", "data/master")
    assert r.returncode == 3 and "does not exist here" in r.stdout + r.stderr
