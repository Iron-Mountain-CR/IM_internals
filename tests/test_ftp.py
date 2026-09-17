"""
Tests for im_internals.ftp.Ftp, using a DummyFTP stand-in (below) in place of a real ftplib.FTP
connection so no network/FTP server is needed.
"""
import os
import ftplib
import pytest
from pathlib import Path
from im_internals.ftp import Ftp


# ----- Dummy socket to satisfy the post-connect keepalive setup -----
class DummySocket:
    def setsockopt(self, *args, **kwargs):
        pass

    def ioctl(self, *args, **kwargs):
        pass


# ----- Dummy FTP to simulate server behavior -----
class DummyFTP:
    def __init__(self):
        self.connected = False
        self.logged_in = False
        self.stored = []
        self.retrieved = []
        self.deleted = []
        self.renamed = []
        self.files = []
        self.sizes = {}
        self.sock = DummySocket()
        self.timeout = None

    def connect(self, host, port, timeout=None):
        self.connected = (host, port)
        self.timeout = timeout

    def login(self, user, passwd):
        if passwd == 'bad':
            raise ftplib.error_perm("530 Login incorrect")
        self.logged_in = (user, passwd)

    def quit(self):
        self.connected = False
        self.logged_in = False

    def rename(self, fromname, toname):
        # Simulate remote rename
        self.renamed.append((fromname, toname))

    def storbinary(self, cmd, f):
        filename = os.path.basename(cmd.split(' ', 1)[1])
        self.stored.append(filename)

    def nlst(self, path):
        return self.files

    def size(self, filename):
        return self.sizes.get(filename, 0)

    def retrbinary(self, cmd, callback):
        filename = cmd.split(' ', 1)[1]
        callback(b'data')
        self.retrieved.append(filename)

    def delete(self, filename):
        self.deleted.append(filename)


@pytest.fixture(autouse=True)
def patch_ftplib(monkeypatch, tmp_path):
    # Patch FTP class
    monkeypatch.setattr(ftplib, 'FTP', lambda: DummyFTP())
    # Create local folders (not used for move_files now)
    files_folder = tmp_path / 'files'
    gets_folder = tmp_path / 'gets'
    log_folder = tmp_path / 'logs'
    files_folder.mkdir()
    gets_folder.mkdir()
    log_folder.mkdir()
    return str(files_folder), str(gets_folder), str(log_folder)


# ----- Initialization tests -----
def test_init_bad_hostname(patch_ftplib):
    files, gets, logs = patch_ftplib
    # host_dots assertion expects host_dots as str and ==3 fails
    with pytest.raises(AssertionError):
        Ftp('127.0.01', 'u', 'p', files, gets, '/remote', logs,
            'log.log', port=21)


def test_init_bad_port(patch_ftplib):
    files, gets, logs = patch_ftplib
    # port must be int
    with pytest.raises(AssertionError):
        Ftp('1.1.1.1', 'u', 'p', files, gets, '/remote', logs,
            'log.log', port='21')


def test_init_valid(patch_ftplib):
    files, gets, logs = patch_ftplib
    # valid four-segment host
    # Monkey-patch hostname validation by providing exactly 4 dots in string
    # (host_dots must be str and equal '3', but code likely fixed)
    ftp = Ftp('192.168.0.1', 'u', 'p', files, gets, '/rem', logs,
              "log.log", port=21)
    assert ftp.hostname == '192.168.0.1'
    assert ftp.port == 21
    assert ftp.files == files
    assert ftp.remote == '/rem'
    assert ftp.get_f == gets
    assert ftp.log_folder == logs
    assert ftp.val_regex == ""


# ----- Property and connection tests -----
def test_ftp_property_connect_and_login(patch_ftplib):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.1.1.1', 'user', 'pass', files, gets, '/rem', logs,
              'log.log', port=21)
    conn = ftp.ftp
    assert conn.connected == ('1.1.1.1', 21)
    assert conn.logged_in == ('user', 'pass')
    # subsequent accesses returns same instance
    assert ftp._ftp is conn


def test_close_connections(patch_ftplib):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              'log.log')
    ftp.close_connections()
    assert ftp._ftp is None


# ----- move_files tests -----
def test_move_files_as_remote_rename(patch_ftplib, monkeypatch):
    files, gets, logs = patch_ftplib

    # Instantiate FTP and trigger connection to get the DummyFTP instance
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/src', logs,
              "log.log", validation_regex=r'two', port=21)

    # Monkey-patch nlst to simulate remote folder contents
    monkeypatch.setattr(ftp.ftp, 'nlst', lambda path: ['/src/one.pdf', '/src/two.pdf', '/src/skip.txt'])

    # Call move_files with empty list to use nlst
    not_matched = ftp.move_files([], '/src', '/dest', 'logger')

    # one.pdf fails regex, two.pdf is renamed remotely
    assert not_matched == ['one.pdf']
    assert ftp.ftp.renamed == [('/src/two.pdf', '/dest/two.pdf')]


# ----- upload_files tests -----
def test_upload_files_filter_and_remove(patch_ftplib, tmp_path):
    files, gets, logs = patch_ftplib
    for name in ['a.txt', 'b.txt', 'c.log']:
        (Path(files)/name).write_text('x')
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              "log.log", validation_regex=r'b', port=21)
    not_matched = ftp.upload_files('.txt', 'lg', remove_files=True)

    assert not_matched == ['a.txt']
    assert ftp.ftp.stored == ['b.txt']
    assert not (Path(files)/'b.txt').exists()


# ----- upload_list_of_files tests -----
def test_upload_list_of_files(patch_ftplib, tmp_path):
    files, gets, logs = patch_ftplib
    for name in ['one.pdf', 'two.pdf']:
        (Path(files)/name).write_bytes(b'd')
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              'log.log', port=21)
    res = ftp.upload_list_of_files(['one.pdf'], 'lg', remove_files=False)
    assert res is None
    assert ftp.ftp.stored == ['one.pdf']


# ----- download_files tests -----
def test_download_files_and_remove(patch_ftplib):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              'log.log', port=21)
    ftp.ftp.files = ['/rem/a.txt', '/rem/b.txt', '/rem/c.log']
    downloaded, _ = ftp.download_files('.txt', 'lg', remove_files=True)
    assert downloaded == ['/rem/a.txt', '/rem/b.txt']
    assert ftp.ftp.deleted == ['/rem/a.txt', '/rem/b.txt']


# ----- get_file_sizes tests -----
def test_get_file_sizes_and_unmatched(patch_ftplib):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              "log.log", validation_regex=r'b', port=21)
    ftp.ftp.files = ['a.txt', 'b.txt']
    ftp.ftp.sizes = {'a.txt': 10, 'b.txt': 20}
    sizes, unmatched = ftp.get_file_sizes('.txt', 'lg')
    assert sizes == {'b.txt': 20}
    assert unmatched == ['a.txt']


# ----- download_out_of_list_files tests -----
def test_download_out_of_list_files(patch_ftplib, tmp_path):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              'log.log', port=21)
    ftp.ftp.files = ['a.txt', 'b.txt', 'c.txt']
    downloaded, unmatched = ftp.download_out_of_list_files(['a.txt'], '.txt', 'lg',
                                                           remove_files=False)
    assert downloaded == ['b.txt', 'c.txt']
    assert unmatched == []


# ----- download_only_list_files tests -----
def test_download_only_list_files(patch_ftplib, tmp_path):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.1.1.1', 'u', 'p', files, gets, '/rem', logs,
              "log.log", validation_regex=r'c', port=21)
    ftp.ftp.files = ['a.txt', 'b.txt', 'c.txt']
    downloaded, unmatched = ftp.download_only_list_files(['c.txt', 'd.txt'], '.txt', 'lg',
                                                         remove_files=True)
    assert downloaded == ['c.txt']
    assert unmatched == []


# ----- Connection Persistence Tests -----
def test_connection_persists_without_close(patch_ftplib, tmp_path):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.2.3.4', 'u', 'p', files, gets, '/r', logs,
              'log.log', port=21)
    # perform an operation without close_conn
    ftp.ftp.files = ['/r/test.txt']
    result = ftp.download_files('.txt', 'lg', remove_files=False, close_conn=False)
    # connection should still exist
    assert ftp._ftp is not None


def test_connection_closed_with_flag(patch_ftplib, tmp_path):
    files, gets, logs = patch_ftplib
    ftp = Ftp('1.2.3.4', 'u', 'p', files, gets, '/r', logs,
              'log.log', port=21)
    ftp.ftp.files = ['/r/test.txt']
    # perform an operation with close_conn=True
    result = ftp.download_files('.txt', 'lg', remove_files=False, close_conn=True)
    # connection should be closed
    assert ftp._ftp is None
