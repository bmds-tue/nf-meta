import os

from nf_meta.editor.backend import recent


def test_nothing_remembered_yet():
    assert recent.recent_configs() == []


def test_most_recent_first_without_duplicates(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    recent.remember(a)
    recent.remember(b)
    recent.remember(a)
    assert recent.recent_configs() == [str(a), str(b)]


def test_relative_paths_are_kept_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    recent.remember("sub/mp.yaml")
    assert recent.recent_configs() == [str(tmp_path / "sub" / "mp.yaml")]


def test_urls_are_not_kept():
    recent.remember("https://example.org/mp.yaml")
    assert recent.recent_configs() == []


def test_the_list_is_limited(tmp_path):
    for i in range(recent.MAX_RECENT + 3):
        recent.remember(tmp_path / f"{i}.yaml")
    paths = recent.recent_configs()
    assert len(paths) == recent.MAX_RECENT
    assert paths[0] == str(tmp_path / f"{recent.MAX_RECENT + 2}.yaml")


def test_forget(tmp_path):
    recent.remember(tmp_path / "a.yaml")
    recent.remember(tmp_path / "b.yaml")
    recent.forget(str(tmp_path / "a.yaml"))
    assert recent.recent_configs() == [str(tmp_path / "b.yaml")]


def test_unreadable_list_counts_as_empty():
    recent.recent_file().parent.mkdir(parents=True)
    recent.recent_file().write_text("{not json")
    assert recent.recent_configs() == []


def test_kept_in_the_state_dir():
    assert recent.recent_file() == recent.recent_file().parents[1] / "nf-meta" / "recent-configs.json"
    assert str(recent.recent_file()).startswith(os.environ["XDG_STATE_HOME"])


def test_a_failing_write_is_ignored(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocker))  # a file where the folder should be
    recent.remember(tmp_path / "a.yaml")
    assert recent.recent_configs() == []
