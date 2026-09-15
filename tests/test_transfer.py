"""
Tests for im_internals.transfer.

Thin stub: only covers get_unique_filename()'s basic collision-suffix behavior. Does not test
robust_move, recursive_folder_lookup, move_folder_content, or the Move class's fluent API
despite importing them - see the trailing comment noting they're intended but not yet written.
"""
import os
import tempfile
import pytest
from im_internals.transfer import get_unique_filename, robust_move, recursive_folder_lookup, move_folder_content, Move

def test_get_unique_filename(tmp_path):
    file = tmp_path / "a.txt"
    file.write_text("x")
    new = get_unique_filename(str(tmp_path), "a.txt")
    assert new.startswith("a_1")

# ... more tests covering recursive_folder_lookup, Move.move_files_or_folders, etc.
