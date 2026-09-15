"""
Sanitize
========
Two independent utilities for cleaning up scanned-file output: stripping/normalizing
disallowed characters from a string (:func:`sanitize_string`, backed by
:class:`SanitizationConfig`'s default character list/diacritic map), and detecting
duplicate files across a folder tree by name (:func:`find_duplicate`).

Usage::

    from im_internals.sanitize import sanitize_string, find_duplicate
    clean_name = sanitize_string("Fïle Nãme!!")
    dupes = find_duplicate(root_folder, file_types=(".pdf", ".tif"))
"""
import os
import re
from collections import defaultdict
from typing import Tuple, Dict, List, Optional

from . import logging as pl


class SanitizationConfig:
    """
    Contains default settings for sanitization.

    UNALLOWED_CHARS is a list of characters that should be removed.
    UNALLOWED_WORD_CHAR is a dictionary mapping characters (usually with diacritics)
    to their normalized replacements.

    These values can be overridden by either directly assigning new values to the class
    variables or by subclassing SanitizationConfig.
    """
    UNALLOWED_CHARS = [
        "!", '"', "#", "$", "%", "&", "'", "(", ")", "*", "+", ",", "/", ":", ";",  "<", "=", ">", "?", "@", "[", "\\",
        "]", "^", "`", "{", "|", "}", "~", "¡", "£", "§", "°", "µ", "¶", "´", "˂", ";", "˃", "˄", "˅", "÷", "×", "ß",
        "¤", "˝", "˙", "˛", "˘", "€", "˙", "˝", "–", "—", "‐"
    ]

    UNALLOWED_WORD_CHAR = {
        "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A", "Å": "A", "Ç": "C", "È": "E", "É": "E", "Ê": "E", "Ë": "E",
        "Ì": "I", "Í": "I", "Î": "I", "Ï": "I", "Ð": "D", "Ñ": "N", "Ò": "O", "Ó": "O", "Ô": "O", "Õ": "O", "Ö": "O",
        "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U", "Ý": "Y", "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
        "ç": "c", "è": "e", "é": "e", "ê": "e", "ë": "e", "ì": "i", "í": "i", "î": "i", "ï": "i", "ð": "d", "ñ": "n",
        "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o", "ù": "u", "ú": "u", "û": "u", "ü": "u", "ý": "y", "þ": "p",
        "ÿ": "y", "Ā": "A", "ā": "a", "Ă": "A", "ă": "a", "Ą": "A", "ą": "a", "Ć": "C", "ć": "c", "Ĉ": "C", "ĉ": "C",
        "Ċ": "C", "ċ": "c", "Č": "C", "č": "c", "Ď": "D", "ď": "d", "Đ": "D", "đ": "d", "Ē": "E", "ē": "e", "Ĕ": "E",
        "ĕ": "e", "Ė": "E", "ė": "e", "Ę": "E", "ę": "E", "Ě": "E", "ě": "e", "Ĝ": "G", "ĝ": "g", "Ğ": "G", "ğ": "g",
        "Ġ": "G", "ġ": "g", "Ģ": "G", "ģ": "g", "Ĥ": "H", "ĥ": "h", "Ĩ": "I", "ĩ": "i", "Ī": "I", "ī": "i", "Ĭ": "I",
        "ĭ": "i", "Į": "I", "į": "i", "İ": "I", "ı": "i", "Ĵ": "J", "ĵ": "j", "Ķ": "K", "ķ": "k", "Ĺ": "L", "ĺ": "l",
        "Ļ": "L", "ļ": "l", "Ľ": "L", "ľ": "l", "Ŀ": "L", "ŀ": "l", "Ł": "L", "ł": "l", "Ń": "N", "ń": "N", "Ņ": "N",
        "ņ": "n", "Ň": "N", "ň": "n", "ŉ": "n", "Ō": "O", "ō": "o", "Ŏ": "O", "ŏ": "o", "Ő": "O", "ő": "o", "Ŕ": "R",
        "ŕ": "r", "Ŗ": "R", "ŗ": "R", "Ř": "R", "ř": "r", "Ś": "S", "ś": "s", "Ŝ": "S", "ŝ": "s", "Ş": "S", "ş": "s",
        "Š": "S", "š": "s", "Ţ": "T", "ţ": "t", "Ť": "T", "ť": "t", "Ũ": "U", "ũ": "u", "Ū": "U", "ū": "u", "Ŭ": "U",
        "ŭ": "u", "Ů": "U", "ů": "U", "Ű": "U", "ű": "u", "Ų": "Y", "ų": "y", "Ŵ": "W", "ŵ": "w", "Ŷ": "Y", "ŷ": "y",
        "Ÿ": "Y", "Ź": "Z", "ź": "z", "Ż": "Z", "ż": "z", "Ž": "Z", "ž": "z", "Ǎ": "A", "ǎ": "a", "Ǐ": "i", "ǐ": "i",
        "Ǒ": "o", "ǒ": "o", "Ǔ": "u", "ǔ": "u", "Ǧ": "G", "ǧ": "G", "Ǩ": "K", "ǩ": "k", "Ȁ": "A", "ȁ": "a", "Ȃ": "A",
        "ȃ": "a", "Ȅ": "E", "ȅ": "e", "Ȇ": "E", "ȇ": "e", "Ȉ": "I", "ȉ": "i", "Ȋ": "I", "ȋ": "i", "Ȍ": "i", "ȍ": "o",
        "Ȏ": "O", "ȏ": "o", "Ȑ": "R", "ȑ": "r", "Ȓ": "R", "ȓ": "r", "Ȕ": "U", "ȕ": "u", "Ȗ": "U", "ȗ": "u", "Ș": "S",
        "ș": "s", "Ț": "T", "ț": "t", "Ȟ": "H", "ȟ": "h"
    }


def sanitize_string(text: str, unallowed_chars: List[str] = None, unallowed_word_char: Dict[str, str] = None) -> str:
    """
    Sanitizes the given text by removing characters listed in unallowed_chars and
    replacing characters according to the unallowed_word_char mapping.

    If unallowed_chars or unallowed_word_char are not provided, defaults from
    SanitizationConfig are used.

    :param text: The string to sanitize.
    :type text: str
    :param unallowed_chars: Optional custom list of characters to remove.
    :type unallowed_chars: list | None
    :param unallowed_word_char: Optional custom mapping for character replacements.
    :type unallowed_word_char: dict | None
    :return: The sanitized string.
    :rtype: str
    :raises TypeError: If text is not a string.
    """
    try:
        if not isinstance(text, str):
            raise TypeError(f"Expected text to be str, got {type(text)}")
        chars = unallowed_chars if unallowed_chars is not None else SanitizationConfig.UNALLOWED_CHARS
        mapping = unallowed_word_char if unallowed_word_char is not None else SanitizationConfig.UNALLOWED_WORD_CHAR
        sanitized_chars = []
        for char in text:
            if char in chars:
                continue
            sanitized_chars.append(mapping.get(char, char))
        return "".join(sanitized_chars)
    except Exception as e:
        pl.error(f"Error sanitizing string: {e}")
        raise


def find_duplicate(folder_path: str, file_types: Tuple[str, ...], duplicate_ext: Optional[str] = r" \(\d+\).",
                   duplicate_separators: Optional[Tuple[str, ...]] = (" ", "_")) -> Dict[str, List[str]]:
    """
    Scan `folder_path` for files ending with any of `file_types` and
    return a dict mapping each detected base name to list of full file paths
    that share that base (i.e. the original plus its duplicates).

    :param folder_path: Top-level folder to recurse into.
    :type folder_path: str
    :param file_types: Tuple of file extensions (e.g. (".tif", ".pdf")).
    :type file_types: tuple[str, ...]
    :param duplicate_ext: Regex (without $) matching duplicates like " (2)".
    :type duplicate_ext: str, optional
    :param duplicate_separators: Tuple of separators for dynamic prefix grouping.
    :type duplicate_separators: tuple[str, ...], optional
    :return: Dict mapping base name to a list of file paths with duplicates.
    :rtype: dict[str, list[str]]
    :raises OSError: If folder_path does not exist or is inaccessible.
    :raises re.error: If duplicate_ext regex is invalid.
    """
    try:
        if not os.path.isdir(folder_path):
            raise OSError(f"Folder path does not exist: {folder_path}")

        # 1) Gather all matching files
        name_to_paths: Dict[str, List[str]] = defaultdict(list)
        for dirpath, _, filenames in os.walk(folder_path):
            for fn in filenames:
                if fn.lower().endswith(file_types):
                    name = fn[: fn.rfind(".")]
                    full = os.path.join(dirpath, fn)
                    name_to_paths[name].append(full)

        # 2) Plain-duplicate pass: same exact name in >1 folder
        grouped: Dict[str, List[str]] = defaultdict(list)
        for name, paths in name_to_paths.items():
            if len(paths) > 1:
                grouped[name].extend(paths)

        # 3) First-pass grouping: strip off numbered-duplicate suffixes
        if duplicate_ext:
            num_pat = re.compile(duplicate_ext + r"$")
            for name, paths in name_to_paths.items():
                base = num_pat.sub("", name)
                if base != name:
                    grouped[base].extend(paths)
                    grouped[base].extend(name_to_paths.get(base, []))

        # 4) Second-pass grouping: dynamic prefix-based
        if duplicate_separators:
            candidate: Dict[str, List[str]] = defaultdict(list)
            for name in name_to_paths:
                for sep in duplicate_separators:
                    for m in re.finditer(re.escape(sep), name):
                        prefix = name[: m.start()]
                        candidate[prefix].append(name)

            used_names = set()
            for prefix, names in sorted(candidate.items(), key=lambda kv: -len(kv[0])):
                uniq = set(names)
                if len(uniq) <= 1:
                    continue
                paths = []
                for nm in uniq:
                    paths.extend(name_to_paths[nm])
                if len(paths) > 1 and not any(nm in used_names for nm in uniq):
                    grouped[prefix].extend(paths)
                    used_names.update(uniq)

        # 5) Filter & dedupe final groups
        result: Dict[str, List[str]] = {}
        for base, paths in grouped.items():
            unique_paths = sorted(set(paths))
            if len(unique_paths) > 1:
                result[base] = unique_paths

        return result
    except Exception as e:
        pl.error(f"Error finding duplicates: {e}")
        raise
