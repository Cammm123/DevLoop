import subprocess

from devloop_collector.gitmeta import latest_commit_changed_files, snapshot


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_git_metadata_extraction_without_content_or_remote(tmp_path):
    repo = tmp_path / "private-project"
    repo.mkdir()
    git(repo, "init", "-b", "feature/privacy")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    (repo / "secret.py").write_text("TOP_SECRET_SOURCE = True\n")
    (repo / "other.txt").write_text("private content\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "secret commit message")
    git(repo, "remote", "add", "origin", "https://token@example.invalid/private.git")
    (repo / "secret.py").write_text("changed secret source\n")
    (repo / "untracked.txt").write_text("not readable telemetry\n")

    metadata = snapshot(repo)
    assert metadata.project == "private-project"
    assert metadata.branch == "feature/privacy"
    assert metadata.commit_count == 1
    assert metadata.changed_files == 2
    assert latest_commit_changed_files(repo) == 2
    rendered = repr(metadata)
    assert "TOP_SECRET" not in rendered
    assert "token@example" not in rendered
    assert "secret commit message" not in rendered


def test_git_counts_second_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    for index in range(2):
        (repo / f"f{index}").write_text(str(index))
        git(repo, "add", ".")
        git(repo, "commit", "-m", f"c{index}")
    assert snapshot(repo).commit_count == 2
    assert latest_commit_changed_files(repo) == 1
