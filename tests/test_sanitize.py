"""
Tests for im_internals.sanitize: sanitize_string() (character/punctuation/diacritic cleanup)
and find_duplicate() (grouping filenames by numbered-suffix or prefix-separator patterns,
including recursive directory search and invalid-folder/invalid-regex error handling).
"""
import os
import pytest
from im_internals.sanitize import sanitize_string, find_duplicate, SanitizationConfig


def test_sanitize_string_empty_and_custom():
    # empty string remains empty
    assert sanitize_string("") == ""
    # custom unallowed chars and mapping
    text = "abcXYZ"
    custom_chars = ['X', 'Z']
    custom_map = {'Y': 'y'}
    result = sanitize_string(text, unallowed_chars=custom_chars, unallowed_word_char=custom_map)
    # X and Z removed, Y mapped to lowercase, others unchanged
    assert result == 'abcy'


@ pytest.mark.parametrize("input,expected", [
    ("123!@#abc", "123abc"),            # remove punctuation
    ("ÄÖÜäöüß", "AOUaou"),              # German umlauts and ß
    ("–—‐", ""),                       # dash variants (if in unallowed)
])
def test_sanitize_string_various(input, expected):
    assert sanitize_string(input) == expected


def test_sanitize_string_type_error():
    with pytest.raises(TypeError):
        sanitize_string(123)


# ----- find_duplicate tests -----
def write_files(base, names):
    for name in names:
        path = base / name
        path.write_text('x')


def test_find_duplicate_numbered(tmp_path):
    folder = tmp_path / 'num'
    folder.mkdir()
    # files with numbered suffix
    write_files(folder, ['a.txt', 'a (1).txt', 'a (2).txt', 'b.txt'])
    dups = find_duplicate(str(folder), ('.txt',), duplicate_ext=r' \(\d+\)', duplicate_separators=())
    # base 'a' has 3 paths
    assert 'a' in dups
    assert len(dups['a']) == 3
    # 'b' not duplicated
    assert 'b' not in dups


def test_find_duplicate_prefix(tmp_path):
    folder = tmp_path / 'pref'
    folder.mkdir()
    # prefix patterns: report_v1, report_v2, report_final
    write_files(folder, ['report_v1.pdf', 'report_v2.pdf', 'summary.pdf'])
    # use '_' separator to group by 'report'
    dups = find_duplicate(str(folder), ('.pdf',), duplicate_ext=None, duplicate_separators=('_',))
    # prefix 'report' groups two files
    assert 'report' in dups
    assert sorted([os.path.basename(p) for p in dups['report']]) == ['report_v1.pdf', 'report_v2.pdf']
    # summary not grouped
    assert 'summary' not in dups


def test_find_duplicate_recursive(tmp_path):
    # nested folders with same file name
    root = tmp_path / 'root'
    sub = root / 'sub'
    sub2 = root / 'sub2'
    root.mkdir()
    sub.mkdir()
    sub2.mkdir()
    write_files(root, ['c.txt'])
    write_files(sub, ['c.txt'])
    write_files(sub2, ['d.txt'])
    dups = find_duplicate(str(root), ('.txt',))
    # 'c' duplicated across directories
    assert 'c' in dups and len(dups['c']) == 2
    assert 'd' not in dups


def test_find_duplicate_invalid_folder(tmp_path):
    # non-existent path
    with pytest.raises(OSError):
        find_duplicate(str(tmp_path / 'no'), ('.txt',))


def test_find_duplicate_bad_regex(tmp_path):
    folder = tmp_path / 'r'
    folder.mkdir()
    (folder / 'x.txt').write_text('x')
    # invalid regex should raise re.error
    with pytest.raises(Exception):
        find_duplicate(str(folder), ('.txt',), duplicate_ext='(unclosed[')
