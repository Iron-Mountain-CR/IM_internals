"""
FTP
===
Plain (non-SFTP) FTP transfer helper built on `ftplib`, mirroring the shape of `im_internals.sftp`
for scripts whose remote server only speaks FTP.

Usage::

    from im_internals.ftp import Ftp

    ftp = Ftp(hostname="10.0.0.1", username="user", password="pw",
              files_folder=r"C:\\upload", get_folder=r"C:\\download",
              remote_folder="/incoming", log_folder=r"C:\\logs", log_name="job.log")
    ftp.upload_files(file_type=".pdf", logger_name="unused")
    ftp.close_connections()

All transfer methods are decorated with `ftp_retry` (3 attempts, exponential backoff) and log via
the shared `im_internals.logging` singleton rather than the `logger_name` parameter, which is kept
only for call-site backward compatibility with the pre-`im_internals` API. `hostname` is asserted to
contain exactly 3 dots (a loose IPv4-shape check, not real validation — e.g. "a.b.c.d" or
"999.999.999.999" would also pass), so a real DNS hostname without dots would be rejected but is not
guaranteed to actually be a valid IP.

`connect()` is bounded by `connect_timeout` (default 60s - higher than `Sftp`'s since this same
timeout also applies to ftplib's data-transfer socket, not just the initial connect) - added
2026-09-17 because a connection that silently died (VPN blip, firewall idle timeout) previously had
no way to be noticed: the socket never errors on its own, so the next command, or even
`close_connections()`/`__del__` at script end, could block forever. `ftplib` has no protocol-level
keepalive of its own (unlike `im_internals.sftp.Sftp`'s SSH-level `set_keepalive`), so OS-level TCP
keepalive is enabled on the control-connection socket instead via `_enable_tcp_keepalive()` - a
best-effort mitigation, not as reliable as an application-level heartbeat. `connect_timeout` is an
optional constructor kwarg with a default, so existing call sites are unaffected.
"""
import ftplib
import logging
import os
import re
import socket
from typing import List, Tuple, Dict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, before_sleep_log

from . import logging as pl

# Standard logger kept solely for tenacity's before_sleep_log (requires stdlib Logger)
_tenacity_logger = logging.getLogger(__name__)

# retry decorator for FTP operations, using Tenacity
ftp_retry = retry(
    retry=retry_if_exception(lambda exc: isinstance(exc, ftplib.all_errors)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=10),
    reraise=True,
    before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING)
)


def _enable_tcp_keepalive(sock, idle_seconds: int = 30, interval_seconds: int = 10) -> None:
    """Turn on OS-level TCP keepalive on an already-connected socket.

    `ftplib` has no application-level heartbeat (unlike `im_internals.sftp.Sftp`'s SSH keepalive), so
    this is the closest equivalent: it lets the OS notice a silently-dropped connection (VPN blip,
    firewall idle timeout) and fail fast on it, instead of a later read/write or close() blocking
    forever on a socket that never sees an error. Best-effort only - failures are logged and
    swallowed since a missing keepalive should not stop the connection from being usable.
    """
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):
            # Windows: (onoff, idle_time_ms, interval_ms) - every script in this repo runs on Windows.
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle_seconds * 1000, interval_seconds * 1000))
        elif hasattr(socket, "TCP_KEEPIDLE"):
            # Linux fallback, kept for completeness even though this repo is Windows-only today.
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle_seconds)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_seconds)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except OSError as e:
        pl.warn(f"Could not enable TCP keepalive on FTP socket: {e}")


class Ftp:
    """
    A class for interacting with FTP servers, including file uploads, downloads, and remote file management.

    :param hostname: The hostname of the FTP server.
    :type hostname: str
    :param username: The username for FTP login.
    :type username: str
    :param password: The password for FTP login.
    :type password: str
    :param files_folder: Local folder path containing the files to be processed.
    :type files_folder: str
    :param get_folder: Local folder path where downloaded files will be stored.
    :type get_folder: str
    :param remote_folder: Remote folder path on the FTP server.
    :type remote_folder: str
    :param log_folder: Folder path where log files will be saved.
    :type log_folder: str
    :param log_name: Log filename (must end with .log).
    :type log_name: str
    :param validation_regex: Regex that will be used for filtering the names of file or folders.
    :type validation_regex: str
    :param port: The port number for the FTP server (default: 21).
    :type port: int
    :param connect_timeout: Max seconds for the control-connection socket - covers both the initial
        `connect()` and, since `ftplib` reuses the same timeout for data-transfer sockets, any silent
        stall during a transfer.
    :type connect_timeout: float, optional
    """

    def __init__(self, hostname: str, username: str, password: str, files_folder: str, get_folder: str,
                 remote_folder: str, log_folder: str, log_name: str, validation_regex="", port: int = 21,
                 connect_timeout: float = 60.0):
        """
        Initializes the FTP class with the given connection details, local and remote folder paths, and logging
        settings.

        :param hostname: The hostname or IP address of the FTP server.
        :type hostname: str
        :param username: The username for the FTP login.
        :type username: str
        :param password: The password for the FTP login.
        :type password: str
        :param files_folder: Local folder path containing the files to be processed or uploaded.
        :type files_folder: str
        :param get_folder: Local folder path where downloaded files will be stored.
        :type get_folder: str
        :param remote_folder: The remote folder path on the FTP server.
        :type remote_folder: str
        :param log_folder: The folder path where log files will be saved.
        :type log_folder: str
        :param log_name: The log filename (must end with .log).
        :type log_name: str
        :param validation_regex: Regex that will be used for filtering the names of file or folders.
        :type validation_regex: str
        :param port: The port number for the FTP connection (default is 21).
        :type port: int, optional
        :param connect_timeout: Max seconds to wait on the control/data sockets before raising,
            instead of blocking forever on an unreachable host or a connection that went silently
            dead mid-transfer. Defaults to 60s (higher than `Sftp`'s 30s default since this same
            value also bounds data transfers here, not just the handshake).
        :type connect_timeout: float, optional
        """
        host_dots = sum([1 for dot in hostname if dot == "."])

        assert isinstance(hostname, str) and host_dots == 3, \
            "Hostname must be a string with structure XXX.XXX.XXX.XXX!"
        assert isinstance(username, str), "Username must be a string!"
        assert isinstance(password, str), "Password must be a string!"
        assert isinstance(files_folder, str) and os.path.exists(files_folder), \
            "Files folder must be a path string, and the path must be accessible for the device"
        assert isinstance(get_folder, str) and os.path.exists(get_folder), \
            "Get folder must be a path string, and the path must be accessible for the device"
        assert isinstance(remote_folder, str) and "/" in remote_folder, \
            "Remote folder must be a path string and it must contains '/' as FTP path should be 'Folder/File' structure"
        assert isinstance(log_folder, str) and os.path.exists(log_folder), \
            "Log folder must be a path string, and the path must be accessible for the device!"
        assert isinstance(log_name, str) and log_name.endswith(".log"), \
            "Log filename must be a string that ends with '.log' as file type!"
        assert isinstance(validation_regex, str) and isinstance(re.compile(validation_regex), re.Pattern), \
            "Validation regex must be a string that is actually a readable regex!"
        assert isinstance(port, int), "FTP port must be a integer if it needs to be changes! Otherwise default 21"
        assert isinstance(connect_timeout, (int, float)) and connect_timeout > 0, \
            "Connect timeout must be a positive number of seconds!"

        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.files = files_folder
        self.remote = remote_folder
        self.get_f = get_folder
        self.log_folder = log_folder
        self.log_name = log_name
        self._ftp = None
        self.val_regex = validation_regex
        self.connect_timeout = connect_timeout

    def __del__(self):
        """
        Ensures all connections are closed when the instance is deleted.

        Swallows all exceptions: __del__ can run on a partially-constructed
        instance (an assert failed in __init__ before any attributes were set)
        or during interpreter shutdown (module globals already torn down, e.g.
        ``pl.progress`` needing ``datetime``) - Python already ignores exceptions
        raised here, only printing them as noise, so there is nothing to gain by
        letting them propagate.
        """
        try:
            self.close_connections()
            pl.progress(f"FTP connections for {self.hostname} have been closed upon deletion.")
        except Exception:
            pass

    @property
    def ftp(self):
        """
        Establishes and returns the FTP connection.

        Bounds the connection with ``connect_timeout`` and enables OS-level TCP keepalive on the
        socket - without these, a connection that goes silently dead (VPN blip, firewall idle
        timeout) can leave later commands, or ``close_connections()`` itself, blocked forever since
        the socket never sees an error.

        :return: The FTP connection object.
        :rtype: ftplib.FTP
        :raises ftplib.all_errors: If there is an error during FTP connection or login.
        """
        if self._ftp is None:
            self._ftp = ftplib.FTP()
            self._ftp.connect(host=self.hostname, port=self.port, timeout=self.connect_timeout)
            self._ftp.login(user=self.username, passwd=self.password)
            _enable_tcp_keepalive(self._ftp.sock)
        return self._ftp

    def close_connections(self):
        """
        Closes the FTP connection if it is currently open.
        """
        if getattr(self, "_ftp", None) is not None:
            self._ftp.quit()
            self._ftp = None

    def _log_setup(self, logger_name: str):
        """
        Returns the centralised project logger.

        The ``logger_name`` parameter is accepted for API compatibility but is
        no longer used to create a separate file handler — all log output is
        handled by the project_logging singleton configured at entry-point level.

        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :return: The configured project Logger instance.
        :rtype: project_logging.Logger
        """
        return pl.get()

    @ftp_retry
    def move_files(self, files_list: List[str], start_folder: str, end_folder: str, logger_name: str,
                   close_conn: bool = False) -> None | List[str]:
        """
        Moves files on the FTP server from one folder to another.

        :param files_list: A list of filenames to move.
        :type files_list: list
        :param start_folder: The remote folder path containing the files to move.
        :type start_folder: str
        :param end_folder: The remote folder path where the files will be moved.
        :type end_folder: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: A list of files that did not meet the regex criteria, or None.
        :rtype: None | list
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(start_folder, str) and "/" in start_folder, \
            "Remote folder must be a path string and it must contains '/' as FTP path should be 'Folder/File' structure"
        assert isinstance(end_folder, str) and "/" in end_folder, \
            "Remote folder must be a path string and it must contains '/' as FTP path should be 'Folder/File' structure"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started moving files on FTP")
        try:
            ftp_conn = self.ftp
            if not files_list:
                files_list = [os.path.basename(p) for p in ftp_conn.nlst(start_folder) if p.lower().endswith(".pdf")]
            for file in files_list:
                if not file.lower().endswith(".pdf"):
                    continue
                filename = file[:file.rfind(".")]
                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                    old_remote = f"{start_folder}/{file}"
                    new_remote = f"{end_folder}/{file}"
                    ftp_conn.rename(old_remote, new_remote)
                    pl.progress(f"Moved file {file} to folder {end_folder} on FTP")
                else:
                    pl.warn("File doesn't suit the specified regex structure")
                    not_matched.append(file)

            pl.progress(f"Completed moving files to folder {end_folder} on FTP")
            if not_matched:
                return not_matched

        except Exception as e:
            pl.error(f"Failed to move files on FTP from {start_folder} to {end_folder}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def upload_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                     close_conn: bool = False) -> None | List[str]:
        """
        Uploads files of a specific type from a local folder to the FTP server.

        :param file_type: The type of files to upload (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the local files after successful upload.
        :type remove_files: bool
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: A list of files that did not match the regex validation, or None.
        :rtype: None | list
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started uploading files to FTP")
        try:
            ftp_conn = self.ftp
            for dirpath, _, filenames in os.walk(self.files):
                for file in filenames:
                    if file.lower().endswith(file_type.lower()):
                        filename = file[:file.rfind(".")]
                        if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                            local_path = os.path.join(dirpath, file)
                            remote_path = f"{self.remote}/{file}"
                            with open(local_path, 'rb') as f:
                                ftp_conn.storbinary(f'STOR {remote_path}', f)
                            pl.progress(f"Uploaded file {file} to FTP")

                            if remove_files:
                                os.remove(local_path)
                                pl.progress(f"Removed local file {file}")
                        else:
                            pl.warn("File doesn't suit the specified regex structure")
                            not_matched.append(file)

            pl.progress(f"Completed uploading files to FTP {self.hostname}")
            if not_matched:
                return not_matched

        except Exception as e:
            pl.error(f"Failed to upload files to FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def upload_list_of_files(self, files_list: List[str], logger_name: str, remove_files: bool = False,
                             close_conn: bool = False) -> None | List[str]:
        """
        Uploads a specified list of files to the FTP server.

        :param files_list: A list of filenames to be uploaded from the local directory.
        :type files_list: list
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the local files after successful upload.
        :type remove_files: bool
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: A list of files that did not match the specified regex pattern, if any.
        :rtype: list or None
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started uploading list of files to FTP")
        try:
            ftp_conn = self.ftp
            for file in files_list:
                filename = file[:file.rfind(".")]
                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                    local_path = os.path.join(self.files, file)
                    remote_path = f"{self.remote}/{file}"
                    with open(local_path, 'rb') as f:
                        ftp_conn.storbinary(f'STOR {remote_path}', f)
                    pl.progress(f"Uploaded file {file} to FTP")

                    if remove_files:
                        os.remove(local_path)
                        pl.progress(f"Removed local file {file}")
                else:
                    pl.warn("File doesn't suit the specified regex structure")
                    not_matched.append(file)

            pl.progress(f"Completed uploading list of files to FTP {self.hostname}")
            if not_matched:
                return not_matched

        except Exception as e:
            pl.error(f"Failed to upload list of files to FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def download_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                       close_conn: bool = False) -> Tuple[List[str], List[str]]:
        """
        Downloads files of a specified type from the FTP server.

        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the files from the FTP server after download.
        :type remove_files: bool
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: Tuple of (downloaded_files, not_matched_files).
        :rtype: tuple
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started downloading files from FTP")
        downloaded_files = []
        try:
            ftp_conn = self.ftp
            files = ftp_conn.nlst(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, os.path.basename(file))
                        with open(local_path, 'wb') as f:
                            ftp_conn.retrbinary(f'RETR {file}', f.write)
                        downloaded_files.append(file)
                        pl.progress(f"Downloaded file {file} from FTP")

                        if remove_files:
                            ftp_conn.delete(file)
                            pl.progress(f"Removed file {file} from FTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed downloading files from FTP {self.hostname}")
            return downloaded_files, not_matched

        except Exception as e:
            pl.error(f"Failed to download files from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def get_file_sizes(self, file_type: str, logger_name: str, close_conn: bool = False) \
            -> Tuple[Dict[str, int], List[str]]:
        """
        Retrieves the sizes of files on the FTP server that match the specified type.

        :param file_type: The type of files for which to retrieve sizes (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: Tuple of (file_sizes dict, not_matched list).
        :rtype: tuple
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started reading file sizes on FTP")
        file_sizes = {}
        try:
            ftp_conn = self.ftp
            files = ftp_conn.nlst(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        file_size = ftp_conn.size(file)
                        file_sizes[file] = file_size
                        pl.progress(f"File size for {file} is {file_size} bytes")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed reading file sizes on FTP {self.hostname}")
            return file_sizes, not_matched

        except Exception as e:
            pl.error(f"Failed to read file sizes from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def download_out_of_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                   remove_files: bool = False, close_conn: bool = False) \
            -> Tuple[List[str], List[str]]:
        """
        Downloads files from the FTP server that match file_type and are NOT in files_list.

        :param files_list: A list of filenames to exclude from the download.
        :type files_list: list
        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the files from the FTP server after download.
        :type remove_files: bool
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: Tuple of (downloaded_files, not_matched_files).
        :rtype: tuple
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started downloading files not in the specified list from FTP")
        downloaded_files = []
        try:
            ftp_conn = self.ftp
            files = ftp_conn.nlst(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file not in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, os.path.basename(file))
                        pl.progress(f"Downloading file {file} from FTP")
                        with open(local_path, 'wb') as f:
                            ftp_conn.retrbinary(f'RETR {file}', f.write)
                        downloaded_files.append(file)
                        pl.progress(f"Downloaded file {file} from FTP")

                        if remove_files:
                            ftp_conn.delete(file)
                            pl.progress(f"Deleted file {file} from FTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed downloading files not in the specified list from FTP {self.hostname}")
            return downloaded_files, not_matched

        except Exception as e:
            pl.error(f"Failed to download files not in the list from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def download_only_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                 remove_files: bool = False, close_conn: bool = False) \
            -> Tuple[List[str], List[str]]:
        """
        Downloads files from the FTP server that match file_type and ARE in files_list.

        :param files_list: A list of filenames to download.
        :type files_list: list
        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the files from the FTP server after download.
        :type remove_files: bool
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: Tuple of (downloaded_files, not_matched_files).
        :rtype: tuple
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started downloading only specified files from FTP")
        downloaded_files = []
        try:
            ftp_conn = self.ftp
            files = ftp_conn.nlst(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, os.path.basename(file))
                        pl.progress(f"Downloading file {file} from FTP")
                        with open(local_path, 'wb') as f:
                            ftp_conn.retrbinary(f'RETR {file}', f.write)
                        downloaded_files.append(file)
                        pl.progress(f"Downloaded file {file} from FTP")

                        if remove_files:
                            ftp_conn.delete(file)
                            pl.progress(f"Deleted file {file} from FTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed downloading only specified files from FTP {self.hostname}")
            return downloaded_files, not_matched

        except Exception as e:
            pl.error(f"Failed to download specified files from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()
