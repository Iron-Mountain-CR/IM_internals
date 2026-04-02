import os
import re
import socket
import logging
import paramiko
from typing import List, Tuple, Dict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, before_sleep_log

from . import logging as pl

# Standard logger kept solely for tenacity's before_sleep_log (requires stdlib Logger)
_tenacity_logger = logging.getLogger(__name__)

# retry decorator for SFTP operations, using Tenacity
sftp_retry = retry(
    retry=retry_if_exception(lambda exc: isinstance(exc, (paramiko.SSHException, socket.error, IOError))),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=10),
    reraise=True,
    before_sleep=before_sleep_log(_tenacity_logger, logging.WARNING)
)


class Sftp:
    """
    A class for interacting with SFTP servers, including file uploads, downloads, and remote file management.

    :param hostname: The hostname or IP address of the SFTP server.
    :type hostname: str
    :param username: The username for SFTP login.
    :type username: str
    :param password: The password for SFTP login.
    :type password: str
    :param files_folder: Local folder path containing the files to be processed.
    :type files_folder: str
    :param get_folder: Local folder path where downloaded files will be stored.
    :type get_folder: str
    :param remote_folder: The remote folder path on the SFTP server.
    :type remote_folder: str
    :param log_folder: Folder path where log files will be saved.
    :type log_folder: str
    :param log_name: Log filename (must end with .log).
    :type log_name: str
    :param validation_regex: Regex that will be used for filtering the names of file or folders.
    :type validation_regex: str
    :param port: The port number for the SFTP connection (default: 22).
    :type port: int, optional
    """

    def __init__(self, hostname, username, password, files_folder, get_folder, remote_folder, log_folder,
                 log_name, validation_regex="", port=22):
        """
        Initializes the SFTP class with the given connection details, local and remote folder paths,
        and logging settings.

        :param hostname: The hostname or IP address of the SFTP server.
        :type hostname: str
        :param username: The username for SFTP login.
        :type username: str
        :param password: The password for SFTP login.
        :type password: str
        :param files_folder: Local folder path containing the files to be processed.
        :type files_folder: str
        :param get_folder: Local folder path where downloaded files will be stored.
        :type get_folder: str
        :param remote_folder: The remote folder path on the SFTP server.
        :type remote_folder: str
        :param log_folder: The folder path where log files will be saved.
        :type log_folder: str
        :param log_name: The log filename (must end with .log).
        :type log_name: str
        :param validation_regex: Regex that will be used for filtering the names of file or folders.
        :type validation_regex: str
        :param port: The port number for the SFTP connection (default is 22).
        :type port: int, optional
        """
        host_dots = sum([1 for dot in hostname if dot == "."])

        assert isinstance(host_dots, str) and host_dots == 3, \
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
        assert isinstance(log_name, str) and log_folder.endswith(".log"), \
            "Log filename must be a string that ends with '.log' as file type!"
        assert isinstance(validation_regex, str) and isinstance(re.compile(validation_regex), re.Pattern), \
            "Validation regex must be a string that is actually a readable regex!"
        assert isinstance(port, int), "FTP port must be a integer if it needs to be changes! Otherwise default 21"

        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.files = files_folder
        self.remote = remote_folder
        self.get_f = get_folder
        self.log_folder = log_folder
        self.log_name = log_name
        self._client = None
        self._sftp = None
        self.val_regex = validation_regex

    def __del__(self):
        """
        Ensures all connections are closed when the instance is deleted.
        """
        self.close_connections()
        pl.progress(f"SFTP connections for {self.hostname} have been closed upon deletion.")

    @property
    def client(self):
        """
        Establishes and returns the SSH client connection.

        :return: The SSH client connection object.
        :rtype: paramiko.SSHClient
        :raises paramiko.SSHException: If there is an error during SSH client connection.
        """
        if self._client is None:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(hostname=self.hostname, username=self.username, password=self.password, port=self.port)
        return self._client

    @property
    def sftp(self):
        """
        Establishes and returns the SFTP session.

        :return: The SFTP client session object.
        :rtype: paramiko.SFTPClient
        :raises paramiko.SSHException: If there is an error during SFTP session initialization.
        """
        if self._sftp is None:
            self._sftp = self.client.open_sftp()
        return self._sftp

    def close_connections(self):
        """
        Closes the SFTP and SSH connections if they are currently open.
        """
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def _log_setup(self, logger_name):
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

    @sftp_retry
    def move_files(self, files_list: List[str], start_folder: str, end_folder: str, logger_name: str,
                   close_conn: bool = False) -> None | List[str]:
        """
        Moves files from one folder to another on the SFTP server.

        :param files_list: List of filenames to move. If empty, all files in start_folder are processed.
        :type files_list: list
        :param start_folder: The remote folder path containing the files to be moved.
        :type start_folder: str
        :param end_folder: The remote folder path where the files will be moved.
        :type end_folder: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: A list of files that did not match the regex (if any), otherwise None.
        :rtype: None | list
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(start_folder, str) and "/" in start_folder, \
            "Remote folder must be a path string and it must contains '/' as SFTP path should be 'Folder/File'"
        assert isinstance(end_folder, str) and "/" in end_folder, \
            "Remote folder must be a path string and it must contains '/' as SFTP path should be 'Folder/File'"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started moving files to SFTP")
        try:
            if not files_list:
                files_list = self.sftp.listdir(start_folder)

            for file in files_list:
                if file.lower().endswith(".pdf"):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        pl.progress(f"Started moving file {file} to SFTP")
                        old_file_path = os.path.join(start_folder, file)
                        new_file_path = os.path.join(end_folder, file)
                        self.sftp.rename(oldpath=old_file_path, newpath=new_file_path)
                        pl.progress(f"Moved file {file} to folder {end_folder}")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed moving files to folder {end_folder}")
            if not_matched:
                return not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Error moving files from {start_folder} to {end_folder} on SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def upload_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                     close_conn: bool = False) -> None | List[str]:
        """
        Uploads files of a specific type from a local folder to the SFTP server.

        :param file_type: The type of files to upload (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the local files after successful upload.
        :type remove_files: bool
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: A list of files that did not match the regex (if any), otherwise None.
        :rtype: None | list
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        pl.progress("Started uploading files to SFTP")
        try:
            for dirpath, _, filenames in os.walk(self.files):
                for file in filenames:
                    if file.lower().endswith(file_type.lower()):
                        filename = file[:file.rfind(".")]
                        if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                            local_path = os.path.join(dirpath, file)
                            remote_path = self.remote + f"/{file}"
                            self.sftp.put(localpath=local_path, remotepath=remote_path)
                            pl.progress(f"Uploaded file {file} to SFTP")

                            if remove_files:
                                os.remove(local_path)
                                pl.progress(f"Removed local file {file}")
                        else:
                            pl.warn("File doesn't suit the specified regex structure")
                            not_matched.append(file)

                pl.progress(f"Completed uploading files to the SFTP {self.hostname}")
                if not_matched:
                    return not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Error uploading files to SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def upload_list_of_files(self, files_list: List[str], logger_name: str, remove_files: bool = False,
                             close_conn: bool = False) -> None | List[str]:
        """
        Uploads a specified list of files to the SFTP server.

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

        pl.progress("Started uploading list of files to SFTP")
        try:
            for file in files_list:
                filename = file[:file.rfind(".")]
                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                    local_path = os.path.join(self.files, file)
                    remote_path = self.remote + f"/{file}"
                    pl.progress(f"Uploading file {file} to SFTP")
                    self.sftp.put(localpath=local_path, remotepath=remote_path)
                    pl.progress(f"Uploaded file {file} to SFTP")

                    if remove_files:
                        os.remove(local_path)
                        pl.progress(f"Removed local file {file}")
                else:
                    pl.warn("File doesn't suit the specified regex structure")
                    not_matched.append(file)

            pl.progress(f"Completed uploading files to the SFTP {self.hostname}")
            if not_matched:
                return not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Failed to upload files to SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def download_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                       close_conn: bool = False) -> Tuple[List[str], List[str]]:
        """
        Downloads files of a specified type from the SFTP server.

        :param file_type: The file extension/type to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the files from the SFTP server after download.
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

        pl.progress("Started downloading files from SFTP")
        downloaded_files = []
        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, file)
                        remote_path = self.remote + f"/{file}"
                        self.sftp.get(localpath=local_path, remotepath=remote_path)
                        pl.progress(f"Downloaded file {file} from SFTP")
                        downloaded_files.append(file)

                        if remove_files:
                            self.sftp.remove(remote_path)
                            pl.progress(f"Removed file {file} from SFTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed downloading files from SFTP {self.hostname}")
            return downloaded_files, not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Error downloading files from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def download_out_of_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                   remove_files: bool = False, close_conn: bool = False) -> Tuple[List[str], List[str]]:
        """
        Downloads files from the SFTP server that match file_type and are NOT in files_list.

        :param files_list: A list of filenames to exclude from the download.
        :type files_list: list
        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the files from the SFTP server after download.
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

        pl.progress("Started downloading files not in the given list from SFTP")
        downloaded_files = []
        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file not in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, file)
                        remote_path = self.remote + f"/{file}"
                        pl.progress(f"Downloading file {file} from SFTP")
                        self.sftp.get(localpath=local_path, remotepath=remote_path)
                        downloaded_files.append(file)
                        pl.progress(f"Downloaded file {file} from SFTP")

                        if remove_files:
                            self.sftp.remove(remote_path)
                            pl.progress(f"Removed file {file} from SFTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed downloading files not in the given list from SFTP {self.hostname}")
            return downloaded_files, not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Failed to download files from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def download_only_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                 remove_files: bool = False, close_conn: bool = False) \
            -> Tuple[List[str], List[str]]:
        """
        Downloads files from the SFTP server that match file_type and ARE in files_list.

        :param files_list: A list of filenames to download.
        :type files_list: list
        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param remove_files: If True, deletes the files from the SFTP server after download.
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

        pl.progress("Started downloading only specified files from SFTP")
        downloaded_files = []
        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, file)
                        remote_path = self.remote + f"/{file}"
                        pl.progress(f"Downloading file {file} from SFTP")
                        self.sftp.get(localpath=local_path, remotepath=remote_path)
                        downloaded_files.append(file)
                        pl.progress(f"Downloaded file {file} from SFTP")

                        if remove_files:
                            self.sftp.remove(remote_path)
                            pl.progress(f"Removed file {file} from SFTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed downloading specified files from SFTP {self.hostname}")
            return downloaded_files, not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Failed to download files from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def get_files_sizes(self, file_type: str, logger_name: str, close_conn: bool = False) \
            -> Tuple[Dict[str, int], List[str]]:
        """
        Retrieves the sizes of files on the SFTP server that match the specified type.

        :param file_type: The type of files to retrieve sizes for (e.g., '.txt', '.pdf').
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
        pl.progress("Started reading file sizes on SFTP")
        file_sizes = {}

        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        remote_path = self.remote + f"/{file}"
                        file_sizes[file] = self.sftp.stat(remote_path).st_size
                        pl.progress(f"Read file size for {file} from SFTP")
                    else:
                        pl.warn("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            pl.progress(f"Completed reading file sizes from SFTP {self.hostname}")
            return file_sizes, not_matched

        except (Exception, socket.error) as e:
            pl.error(f"Failed to read file sizes from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def verify_file_hash(self, filename: str, chunk_size: int, first_local_md5_chunk: bytes,
                         last_local_md5_chunk: bytes, logger_name: str, close_conn=False) -> bool:
        """
        Verify the integrity of a remote file on the SFTP server by comparing its MD5 hash
        of the first and last chunks with precomputed local MD5 digests.

        :param filename: Name of the file on the SFTP server to verify.
        :type filename: str
        :param chunk_size: Number of bytes to hash at each end of the file.
        :type chunk_size: int
        :param first_local_md5_chunk: The MD5 digest of the first chunk_size bytes of the local file.
        :type first_local_md5_chunk: bytes
        :param last_local_md5_chunk: The MD5 digest of the last chunk_size bytes of the local file.
        :type last_local_md5_chunk: bytes
        :param logger_name: Unused; kept for backward compatibility.
        :type logger_name: str
        :param close_conn: If True, closes all open connections after completing.
        :type close_conn: bool
        :return: True if both remote chunk MD5s match the local digests.
        :rtype: bool
        """
        pl.progress("Started file hash verification.")

        assert isinstance(filename, str) and filename.rfind(".") != -1, (
            "Filename must consist of the file ending as well!"
        )
        assert isinstance(chunk_size, int) and chunk_size > 256 and chunk_size != 0, (
            "Chunk size must be at the minimum number 256 or 0 for whole file hash!!"
        )
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        try:
            self.sftp.chdir(self.remote)
            pl.progress(f"Changed path to {self.remote}")

            with self.sftp.open(filename=filename, mode="r") as sftp_file:
                if sftp_file.seekable():
                    first_data_chunk = sftp_file.read(chunk_size)
                    file_size = sftp_file.stat().st_size
                    pl.log_kv("ZIP file size", bytes=file_size)
                    sftp_file.seek(file_size - chunk_size)
                    last_data_chunk = sftp_file.read(chunk_size)
                    pl.progress(
                        f"Prepared remote data chunks: First => {first_data_chunk!r} | Last => {last_data_chunk!r}"
                    )
                else:
                    raise IOError("File is not Seekable to verify its HASH!! Verify file path and file completeness")

            pl.progress("Completed verifying file MD5 hash")
            return first_data_chunk == first_local_md5_chunk and last_data_chunk == last_local_md5_chunk

        except (Exception, socket.error) as e:
            pl.error(f"Failed to read file sizes from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()
