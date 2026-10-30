import pytest

from nf_meta.editor.backend.files import list_folder


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "Configs").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "mp.yaml").write_text("x")
    (tmp_path / "Other.YML").write_text("x")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / ".hidden.yaml").write_text("x")
    return tmp_path


def names(listing):
    return [(e["kind"], e["name"]) for e in listing["entries"]]


def test_folders_first_then_config_files_without_hidden_ones(folder):
    listing = list_folder(str(folder), folder)
    assert names(listing) == [("folder", "Configs"), ("folder", "runs"), ("file", "mp.yaml"), ("file", "Other.YML")]
    assert listing["path"] == str(folder.resolve())
    assert listing["parent"] == str(folder.resolve().parent)
    assert listing["entries"][2]["path"] == str(folder.resolve() / "mp.yaml")


def test_all_files(folder):
    assert ("file", "notes.txt") in names(list_folder(str(folder), folder, all_files=True))


def test_start_and_file_paths(folder):
    assert list_folder(None, folder)["path"] == str(folder.resolve())
    assert list_folder(str(folder / "mp.yaml"), folder)["path"] == str(folder.resolve())


def test_relative_path_from_the_current_directory(folder, monkeypatch):
    monkeypatch.chdir(folder)
    assert list_folder("runs", folder)["path"] == str((folder / "runs").resolve())


def test_root_has_no_parent(tmp_path):
    assert list_folder("/", tmp_path)["parent"] is None


def test_missing_folder(folder):
    with pytest.raises(FileNotFoundError):
        list_folder(str(folder / "nope"), folder)
