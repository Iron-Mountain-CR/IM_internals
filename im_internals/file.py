"""
File
====
Single-file metadata and sanitization helper. Replaces the old
`_Frequently_used.FILE_Class_prod.File` (breaking change: old ctor took
`(folder_path, filename)`, this one takes one combined `file_path`; attrs
renamed `.file_name`->`.name`, `.file_ext`->`.extension`, `.md_hash`->`.md5`).

Usage::

    from im_internals.file import File
    f = File("C:/data/report.PDF")
    f.name        # "report"
    f.extension   # "pdf"
    f.md5         # lazily computed and cached on first access
    f.sanitize_filename()  # renames on disk if the name has disallowed chars
"""
from pathlib import Path
import hashlib
import csv
import xml.etree.ElementTree as ET
import pypdf

from . import logging as pl
from .sanitize import sanitize_string


class File:
    """
    File utility class for computing metadata and sanitizing various file types.

    :param path: Path to the target file.
    """
    def __init__(self, file_path: str):
        """
        Initialize File object for the given file path.

        :param file_path: Path to the file.
        :raises FileNotFoundError: If the file does not exist.
        """
        try:
            self.path = Path(file_path)
            if not self.path.exists():
                raise FileNotFoundError(f"{self.path} does not exist")
        except Exception as e:
            pl.error(f"Error initializing File for {file_path}: {e}")
            raise

        self._md5 = None  # lazy-computed MD5 hash

    @property
    def name(self) -> str:
        """
        Return the file name without its extension.

        :returns: The stem of the file name.
        """
        return self.path.stem

    @property
    def extension(self) -> str:
        """
        Return the file extension without the leading dot.

        :returns: File extension.
        """
        return self.path.suffix.lstrip('.')

    @property
    def created(self) -> float:
        """
        Return the file creation timestamp.

        :returns: Creation time in seconds since the epoch.
        :raises OSError: If file metadata cannot be accessed.
        """
        try:
            return self.path.stat().st_ctime
        except Exception as e:
            pl.error(f"Error getting creation time for {self.path}: {e}")
            raise

    @property
    def modified(self) -> float:
        """
        Return the last modification timestamp of the file.

        :returns: Modification time in seconds since the epoch.
        :raises OSError: If file metadata cannot be accessed.
        """
        try:
            return self.path.stat().st_mtime
        except Exception as e:
            pl.error(f"Error getting modification time for {self.path}: {e}")
            raise

    @property
    def size(self) -> int:
        """
        Return the file size in bytes.

        :returns: Size of the file in bytes.
        :raises OSError: If file metadata cannot be accessed.
        """
        try:
            return self.path.stat().st_size
        except Exception as e:
            pl.error(f"Error getting size for {self.path}: {e}")
            raise

    @property
    def md5(self) -> str:
        """
        Calculate and cache the MD5 hash of the file.

        :returns: MD5 hex digest string.
        :raises IOError: If the file cannot be read.
        """
        if self._md5 is None:
            try:
                hasher = hashlib.md5()
                with self.path.open("rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hasher.update(chunk)
                self._md5 = hasher.hexdigest()
            except Exception as e:
                pl.error(f"Error calculating MD5 for {self.path}: {e}")
                raise
        return self._md5

    def sanitize_filename(self) -> str:
        """
        Sanitize and rename the file on disk if its name contains disallowed characters.

        :returns: The new sanitized filename.
        :raises OSError: If the file cannot be renamed.
        """
        try:
            clean = sanitize_string(self.path.name)
            if clean != self.path.name:
                new_path = self.path.with_name(clean)
                self.path.rename(new_path)
                pl.progress(f"Renamed file {self.path.name!r} → {clean!r}")
                self.path = new_path
            return self.path.name
        except Exception as e:
            pl.error(f"Error sanitizing filename for {self.path}: {e}")
            raise

    def num_pdf_pages(self) -> int:
        """
        Return the number of pages in a PDF file.

        :returns: Number of pages in the PDF.
        :raises ValueError: If the file extension is not 'pdf'.
        :raises pypdf.errors.PdfReadError: If the PDF cannot be read.
        """
        if self.extension.lower() != "pdf":
            raise ValueError("Not a PDF file")
        try:
            reader = pypdf.PdfReader(str(self.path))
            return len(reader.pages)
        except Exception as e:
            pl.error(f"Error reading PDF pages for {self.path}: {e}")
            raise

    def sanitize_csv(self, encoding: str = "utf-16"):
        """
        Read a CSV, sanitize every cell (except those containing 'PageCount'), and overwrite in-place.

        :param encoding: Encoding used to read and write the CSV. Defaults to 'utf-16'.
        :raises ValueError: If the file extension is not 'csv'.
        :raises IOError: If the file cannot be read or written.
        """
        if self.extension.lower() != "csv":
            raise ValueError("Not a CSV file")
        try:
            rows = []
            with self.path.open("r", encoding=encoding, newline="") as f:
                reader = csv.reader(f, delimiter=",", quoting=csv.QUOTE_NONE)
                for row in reader:
                    if "PageCount" in row:
                        rows.append(row)
                    else:
                        rows.append([sanitize_string(cell) for cell in row])

            with self.path.open("w", encoding=encoding, newline="") as f:
                writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_NONE)
                writer.writerows(rows)

            pl.progress(f"Sanitized CSV metadata in {self.path}")
        except Exception as e:
            pl.error(f"Error sanitizing CSV {self.path}: {e}")
            raise

    def sanitize_xml(self):
        """
        Parse XML, sanitize all text nodes, and overwrite the file.

        :raises ValueError: If the file extension is not 'xml'.
        :raises ET.ParseError: If the XML cannot be parsed.
        :raises IOError: If the file cannot be written.
        """
        if self.extension.lower() != "xml":
            raise ValueError("Not an XML file")
        try:
            tree = ET.parse(str(self.path))
            for elem in tree.iter():
                if elem.text:
                    elem.text = sanitize_string(elem.text)
            tree.write(str(self.path), encoding="utf-8", xml_declaration=True)

            pl.progress(f"Sanitized XML file: {self.path}")
        except Exception as e:
            pl.error(f"Error sanitizing XML {self.path}: {e}")
            raise
