"""
Tests for im_internals.file.File: metadata properties (name/extension/size/timestamps/md5),
PDF page counting, and the sanitize_* helpers (filename/csv/xml character cleanup).
"""
import hashlib
import pytest
from im_internals.file import File
import csv
import xml.etree.ElementTree as ET
from pypdf import PdfWriter


def test_name_extension_created_modified_size(tmp_path):
    # Create a simple file
    file_path = tmp_path / "test.txt"
    content = b"Hello, PDF!"
    file_path.write_bytes(content)

    f = File(str(file_path))
    # name and extension
    assert f.name == "test"
    assert f.extension == "txt"

    # created, modified are floats and reasonable
    created = f.created
    modified = f.modified
    assert isinstance(created, float)
    assert isinstance(modified, float)
    assert modified >= created

    # size
    assert f.size == len(content)


def test_md5(tmp_path):
    data = b"abc123"
    file_path = tmp_path / "hash.bin"
    file_path.write_bytes(data)
    f = File(str(file_path))
    expected = hashlib.md5(data).hexdigest()
    assert f.md5 == expected
    # cached value
    assert f._md5 == expected


def test_sanitize_filename(tmp_path):
    # file name with disallowed characters
    bad_name = "a!b€ß$c.txt"
    path = tmp_path / bad_name
    path.write_text("x")
    f = File(str(path))
    new_name = f.sanitize_filename()
    # expect ! and Đ€ß$ removed
    assert new_name == "abc.txt"
    # file should be renamed on disk
    assert not (tmp_path / bad_name).exists()
    assert (tmp_path / new_name).exists()


def test_num_pdf_pages(tmp_path):
    # create a PDF with 3 pages
    pdf_path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=72, height=72)
    with open(pdf_path, "wb") as out:
        writer.write(out)
    f = File(str(pdf_path))
    assert f.num_pdf_pages() == 3

    # non-pdf extension
    txt = tmp_path / "notpdf.txt"
    txt.write_text("hello")
    f2 = File(str(txt))
    with pytest.raises(ValueError):
        f2.num_pdf_pages()


def test_sanitize_csv(tmp_path):
    # create CSV file
    csv_path = tmp_path / "data.csv"
    rows = [["Val!1", "Two?"], ["PageCount", "5"]]
    # write in utf-16
    with open(csv_path, "w", encoding="utf-16", newline="") as f:
        writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_NONE)
        writer.writerows(rows)

    f = File(str(csv_path))
    f.sanitize_csv(encoding="utf-16")

    # read back
    with open(csv_path, "r", encoding="utf-16", newline="") as f2:
        reader = csv.reader(f2, delimiter=",", quoting=csv.QUOTE_NONE)
        out = list(reader)
    # first row sanitized: remove ! and ?
    assert out[0] == ["Val1", "Two"]
    # second row untouched
    assert out[1] == ["PageCount", "5"]

    # calling on non-csv
    noncsv = tmp_path / "file.txt"
    noncsv.write_text("x")
    f2 = File(str(noncsv))
    with pytest.raises(ValueError):
        f2.sanitize_csv()


def test_sanitize_xml(tmp_path):
    # create XML file
    xml_path = tmp_path / "doc.xml"
    content = '<root><a>He!llo</a><b>Wörld?</b></root>'
    xml_path.write_text(content, encoding="utf-8")
    f = File(str(xml_path))
    f.sanitize_xml()

    # parse and verify
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    assert root.find('a').text == "Hello"
    # Wörld? -> World (remove ? and replace ö)
    assert root.find('b').text == "World"

    # non-xml extension
    nonxml = tmp_path / "doc.txt"
    nonxml.write_text("<x></x>")
    f2 = File(str(nonxml))
    with pytest.raises(ValueError):
        f2.sanitize_xml()
