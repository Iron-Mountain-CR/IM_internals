"""
Tests for im_internals.cfg_commands: locating a .cfg file (find_cfg_file), reading a client
section with [DEFAULT] fallback (read_cfg_file), listing sections (list_sections), and the
-p/-c CLI argument parser (parse_cli_args), including its legacy no-subcommand flag form.
"""
import configparser
import pytest
from im_internals.cfg_commands import (
    find_cfg_file,
    read_cfg_file,
    list_sections,
    parse_cli_args,
)


# ----- helper to create a cfg file with one section -----
def create_cfg(path, name=None, data=None):
    cfg = configparser.ConfigParser()
    if name:
        cfg[name] = data or {}
    # write either directory path + a file name, or a direct file path
    with open(path, "w") as f:
        cfg.write(f)


# ----- find_cfg_file tests -----
def test_find_cfg_file_in_directory(tmp_path):
    cfg_file = tmp_path / "config.CFG"
    create_cfg(str(cfg_file), "X", {"k": "v"})
    assert find_cfg_file(str(tmp_path)) == str(cfg_file)


def test_find_cfg_file_with_file_path(tmp_path):
    cfg_file = tmp_path / "mysettings.cfg"
    create_cfg(str(cfg_file), "A", {"x": "1"})
    # direct .cfg path should return itself
    assert find_cfg_file(str(cfg_file)) == str(cfg_file)


@pytest.mark.parametrize("ext", ["txt", "cfgx", ""])
def test_find_cfg_file_non_cfg_path(tmp_path, ext):
    # path that doesn't end in .cfg
    file = tmp_path / f"file.{ext}"
    file.write_text("data")
    with pytest.raises(FileNotFoundError) as ei:
        find_cfg_file(str(file))
    assert "Path is not a .cfg file" in str(ei.value)


def test_find_cfg_file_missing_cfg_in_dir(tmp_path):
    # empty directory
    with pytest.raises(FileNotFoundError) as ei:
        find_cfg_file(str(tmp_path))
    assert "No .cfg file found in directory" in str(ei.value)


def test_find_cfg_file_missing_file(tmp_path):
    # .cfg extension but file doesn't exist
    fake = tmp_path / "missing.cfg"
    with pytest.raises(FileNotFoundError) as ei:
        find_cfg_file(str(fake))
    assert "Config file not found" in str(ei.value)


# ----- read_cfg_file tests -----
def test_read_cfg_file_success(tmp_path):
    cfg_path = tmp_path / "config.cfg"
    create_cfg(str(cfg_path), "Client", {"a": "1", "b": "2"})
    result = read_cfg_file(str(cfg_path), "Client")
    assert result == {"a": "1", "b": "2"}


def test_read_cfg_file_empty_sections(tmp_path):
    cfg_path = tmp_path / "empty.cfg"
    # create a .cfg with no sections
    create_cfg(str(cfg_path), name=None)
    with pytest.raises(ValueError) as ei:
        read_cfg_file(str(cfg_path), "Anything")
    assert "No sections found in config file" in str(ei.value)


def test_read_cfg_file_missing_section(tmp_path):
    cfg_path = tmp_path / "config.cfg"
    create_cfg(str(cfg_path), "Foo", {"x": "y"})
    with pytest.raises(KeyError) as ei:
        read_cfg_file(str(cfg_path), "Bar")
    assert "Client 'Bar' not found" in str(ei.value)


# ----- list_sections tests -----
def test_list_sections_success(tmp_path):
    cfg_path = tmp_path / "cfg.cfg"
    cfg = configparser.ConfigParser()
    cfg["One"] = {"k": "v"}
    cfg["Two"] = {"x": "y"}
    with open(cfg_path, "w") as f:
        cfg.write(f)
    sections = list_sections(str(cfg_path))
    assert "One" in sections
    assert "Two" in sections


def test_list_sections_no_file(tmp_path):
    # directory with no cfg should bubble FileNotFoundError
    with pytest.raises(FileNotFoundError):
        list_sections(str(tmp_path))


# ----- parse_cli_args tests -----
@pytest.mark.parametrize("args, expected", [
    (["list", "-p", "/path/to/cfg"], {"command": "list", "path": "/path/to/cfg", "client": None}),
    (["get", "-p", "/foo", "-c", "MyClient"], {"command": "get", "path": "/foo", "client": "MyClient"}),
    # allow legacy flags without subcommand; order swapped
    (["-c", "LClient", "-p", "/bar"], {"command": "get", "path": "/bar", "client": "LClient"}),
    (["-p", "/baz", "-c", "Other"], {"command": "get", "path": "/baz", "client": "Other"}),
])
def test_parse_cli_args_valid(args, expected):
    result = parse_cli_args(args)
    assert result == expected


def test_parse_cli_args_missing_subcommand_and_flags():
    # no args at all
    with pytest.raises(SystemExit):
        parse_cli_args([])


def test_parse_cli_args_list_missing_path_is_ok():
    # list has default path="."
    result = parse_cli_args(["list"])
    assert result["command"] == "list"
    assert result["path"] == "."
    assert result["client"] is None


def test_parse_cli_args_get_requires_client():
    # get without -c should error
    with pytest.raises(SystemExit):
        parse_cli_args(["get", "-p", "somewhere"])


def test_parse_cli_args_unknown_subcommand():
    with pytest.raises(SystemExit):
        parse_cli_args(["delete", "-p", ".", "-c", "X"])
