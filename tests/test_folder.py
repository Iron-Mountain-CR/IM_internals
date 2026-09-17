"""
Tests for im_internals.folder.Folder: construction/validation against a real filesystem path,
the full_path property, and the sanitize_name()/sanitize() illegal-character-cleanup pair
(the former previews the cleaned name without renaming on disk, the latter actually renames).
"""
import pytest
from pathlib import Path
from im_internals.folder import Folder


def test_init_valid_folder(tmp_path):
    # Create a directory and initialize Folder
    d = tmp_path / "MyFolder"
    d.mkdir()
    f = Folder(str(d))
    assert f.path == d.resolve()
    assert f.parent == d.parent
    assert f.name == "MyFolder"


def test_init_not_exists(tmp_path):
    # Non-existent path should raise
    non_path = tmp_path / "NoSuchDir"
    with pytest.raises(FileNotFoundError):
        Folder(str(non_path))


def test_full_path_property(tmp_path):
    d = tmp_path / "Some Folder"
    d.mkdir()
    f = Folder(str(d))
    # full_path should be the absolute path
    assert f.full_path == str(d.resolve())
    assert f.full_path.endswith("Some Folder")


def test_sanitize_name_no_change(tmp_path):
    # Name without disallowed characters remains same
    d = tmp_path / "NormalName"
    d.mkdir()
    f = Folder(str(d))
    cleaned = f.sanitize_name()
    assert cleaned == "NormalName"
    # original directory still exists
    assert (tmp_path / "NormalName").exists()


def test_sanitize_name_removes_illegal(tmp_path):
    # Name with punctuation is cleaned
    raw = "Bad!Naßme"
    d = tmp_path / raw
    d.mkdir()
    f = Folder(str(d))
    cleaned = f.sanitize_name()
    # expect illegal chars removed
    assert "!" not in cleaned and "?" not in cleaned
    # but sanitize_name does not rename on disk
    assert (tmp_path / raw).exists()


def test_sanitize_performs_rename(tmp_path):
    # sanitize() should rename the folder on disk
    raw = "Folder!One$"
    expected = "FolderOne"
    d = tmp_path / raw
    d.mkdir()
    f = Folder(str(d))
    new_name = f.sanitize()
    assert new_name == expected
    # old path gone, new exists
    assert not (tmp_path / raw).exists()
    assert (tmp_path / expected).exists()
    # Folder object updated
    assert f.name == expected
    assert f.full_path.endswith(expected)


def test_sanitize_no_change(tmp_path):
    # sanitize() on clean name does nothing
    raw = "CleanFolder"
    d = tmp_path / raw
    d.mkdir()
    f = Folder(str(d))
    new_name = f.sanitize()
    assert new_name == raw
    # folder still exists under same name
    assert (tmp_path / raw).exists()


def test_sanitize_rename_error(tmp_path, monkeypatch):
    # Rename failure should propagate OSError
    # Use a folder name valid on Windows but with characters to sanitize
    raw = "Bad#Dir"
    d = tmp_path / raw
    d.mkdir()
    f = Folder(str(d))
    # Monkey-patch Path.rename to throw
    monkeypatch.setattr(Path, "rename",
                        lambda self, new: (_ for _ in ()).throw(OSError("fail rename")),
                        raising=False
    )
    with pytest.raises(OSError) as excinfo:
        f.sanitize()
    assert "fail rename" in str(excinfo.value)
