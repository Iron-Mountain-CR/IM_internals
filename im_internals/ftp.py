import ftplib
import logging
import os
import re
from typing import List, Tuple, Dict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, before_sleep_log


# retry decorator for FTP operations, using Tenacity
ftp_retry = retry(
    retry=retry_if_exception(lambda exc: isinstance(exc, ftplib.all_errors)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=10),
    reraise=True,
    before_sleep=before_sleep_log( logging.getLogger(__name__), logging.WARNING)
)


class Ftp:
    """
    A class for interacting with FTP servers, including file uploads, downloads, and remote file management.

    The `Ftp` class provides methods for connecting to an FTP server, moving files, uploading files, downloading files,
    and getting file sizes. It supports operations on individual files and lists of files. It also includes logging
    functionality to track each operation's progress and outcome.

    **Attributes**:
        - **hostname** (`str`): The hostname of the FTP server.
        - **username** (`str`): The username for FTP login.
        - **password** (`str`): The password for FTP login.
        - **port** (`int`): The port number for the FTP server (default: 21).
        - **files** (`str`): Local folder path containing the files to be processed.
        - **remote** (`str`): Remote folder path on the FTP server.
        - **get_f** (`str`): Local folder path where downloaded files will be stored.
        - **log_folder** (`str`): Folder path where log files will be saved.
        - **_ftp** (`ftplib.FTP`): Internal FTP connection object.
        - **logger** (`logging.Logger`): Logger object for logging operations.

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
    :param validation_regex: Regex that will be used for filtering the names of file or folders.
    :type validation_regex: str
    :param port: The port number for the FTP server (default: 21).
    :type port: int
    """

    def __init__(self, hostname: str, username: str, password: str, files_folder: str, get_folder: str,
                 remote_folder: str, log_folder: str, log_name: str, validation_regex="", port: int = 21):
        """
        Initializes the FTP class with the given connection details, local and remote folder paths, and logging
        settings.

        This constructor sets up the FTP connection details including the hostname, username, and password. It also
        initializes local and remote folder paths for file operations, sets up the logging directory, and creates
        placeholders for the FTP connection (`_ftp`) and logging object (`logger`).

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
        :param remote_folder: The remote folder path on the FTP server where files will be uploaded or downloaded.
        :type remote_folder: str
        :param log_folder: Optional, the folder path where log files will be saved. If not specified,
                           logging will be disabled.
        :type log_folder: str, optional
        :param validation_regex: Regex that will be used for filtering the names of file or folders.
        :type validation_regex: str
        :param port: Optional, the port number for the FTP connection (default is 21).
        :type port: int, optional
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
        self.logger = None
        self.val_regex = validation_regex

    def __del__(self):
        """
        Ensures all connections are closed when the instance is deleted.
        """
        self.close_connections()
        logging.info(f"FTP connections for {self.hostname} have been closed upon deletion.")

    @property
    def ftp(self):
        """
        Establishes and returns the FTP connection.

        If the FTP connection is not already established, this property initializes the connection and logs in
        using the provided hostname, username, and password.

        :return: The FTP connection object.
        :rtype: ftplib.FTP
        :raises ftplib.all_errors: If there is an error during FTP connection or login.
        """

        if self._ftp is None:
            self._ftp = ftplib.FTP()
            self._ftp.connect(host=self.hostname, port=self.port)
            self._ftp.login(user=self.username, passwd=self.password)
        return self._ftp

    def close_connections(self):
        """
        Closes the FTP connection if it is currently open.

        Ensures that the FTP connection is properly closed and sets the internal connection attribute to `None`.
        """

        if self._ftp is not None:
            self._ftp.quit()
            self._ftp = None

    def _log_setup(self, logger_name: str):
        """
        Sets up and returns a logger for tracking FTP operations.

        This method initializes a logger object if it does not already exist. It configures the logger with a file
        handler to write logs to a specific log file, formats the log entries, and sets the logging level to `INFO`.

        :param logger_name: The name of the logger.
        :type logger_name: str
        :return: A configured logger object.
        :rtype: logging.Logger
        """

        if self.logger is None:
            self.logger = logging.getLogger(logger_name)
            handler = logging.FileHandler(os.path.join(self.log_folder, f"{self.log_name}"), mode="a")
            formatter = logging.Formatter(fmt='%(name)s %(asctime)s |%(funcName)s| %(lineno)d-%(message)s',
                                          datefmt='%d-%m-%Y %H:%M:%S')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        return self.logger

    @ftp_retry
    def move_files(self, files_list: List[str], start_folder: str, end_folder: str, logger_name: str,
                   close_conn: bool = False) -> None | List[str]:
        """
        Moves files on the FTP server from one folder to another.

        This method transfers `.pdf` files from a specified `start_folder` on the local system to a specified
        `end_folder` on the FTP server. If `files_list` is empty, it moves all `.pdf` files in the `start_folder`.
        The method checks files against an optional regular expression (`self.val_regex`) to ensure they meet
        specific naming criteria. Any files that fail to meet the criteria are logged and returned.

        :param files_list: A list of filenames to move. If empty, all `.pdf` files in the `start_folder` are moved.
        :type files_list: list
        :param start_folder: The remote folder path containing the files to move.
        :type start_folder: str
        :param end_folder: The remote folder path on the FTP server where the files will be moved.
        :type end_folder: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of files that did not meet the regex criteria, or `None` if all files were successfully moved.
        :rtype: None | list
        :raises Exception: If an error occurs during the file movement operation.
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(start_folder, str) and "/" in start_folder, \
            "Remote folder must be a path string and it must contains '/' as FTP path should be 'Folder/File' structure"
        assert isinstance(end_folder, str) and "/" in end_folder, \
            "Remote folder must be a path string and it must contains '/' as FTP path should be 'Folder/File' structure"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started moving files on FTP")
        try:
            ftp_conn = self.ftp
            # on empty list: operate on all PDF names returned by the remote folder
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
                    logger.info(f"Moved file {file} to folder {end_folder} on FTP")
                else:
                    logger.warning("File doesn't suit the specified regex structure")
                    not_matched.append(file)

            logger.info(f"Completed moving files to folder {end_folder} on FTP")
            if not_matched:
                return not_matched

        except Exception as e:
            logger.error(f"Failed to move files on FTP from {start_folder} to {end_folder}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def upload_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                     close_conn: bool = False) -> None | List[str]:
        """
        Uploads files of a specific type from a local folder to the FTP server.

        This method traverses the local directory structure (`self.files`) and uploads files that match the specified
        `file_type` to the remote directory (`self.remote`) on the FTP server. Optionally, it removes the local files
        after a successful upload if `remove_files` is set to `True`. Files that do not meet the optional regex
        validation (`self.val_regex`) are logged and returned in a list.

        :param file_type: The type of files to upload (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param remove_files: Optional; If `True`, deletes the local files after successful upload (default is `False`).
        :type remove_files: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of files that did not match the regex validation, or `None` if all files were successfully
                 uploaded.
        :rtype: None | list
        :raises Exception: If an error occurs during the upload process.
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started uploading files to FTP")
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
                            logger.info(f"Uploaded file {file} to FTP")

                            if remove_files:
                                os.remove(local_path)
                                logger.info(f"Removed local file {file}")
                        else:
                            logger.warning("File doesn't suit the specified regex structure")
                            not_matched.append(file)

            logger.info(f"Completed uploading files to FTP {self.hostname}")
            if not_matched:
                return not_matched

        except Exception as e:
            logger.error(f"Failed to upload files to FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def upload_list_of_files(self, files_list: List[str], logger_name: str, remove_files: bool = False,
                             close_conn: bool = False) -> None | List[str]:
        """
        Uploads a specified list of files to the SFTP server.

        This method uploads a predefined list of files from the local directory (`self.files`) to the remote
        directory (`self.remote`) on the SFTP server. For each successfully uploaded file,
        the operation is logged. If `remove_files` is set to `True`, the local files are deleted after
        being uploaded. The method ensures proper connection cleanup, even in case of errors.

        :param files_list: A list of filenames (including extensions) to be uploaded from the local directory.
        :type files_list: list
        :param logger_name: The name of the logger to use for logging the upload process.
        :type logger_name: str
        :param remove_files: Optional; if `True`, deletes the local files after successful upload.
                             Defaults to `False`.
        :type remove_files: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of files that did not match the specified regex pattern, if any.
        :rtype: list or None
        :raises Exception: If an error occurs during the upload process.
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started uploading list of files to FTP")
        try:
            ftp_conn = self.ftp
            for file in files_list:
                filename = file[:file.rfind(".")]
                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                    local_path = os.path.join(self.files, file)
                    remote_path = f"{self.remote}/{file}"
                    with open(local_path, 'rb') as f:
                        ftp_conn.storbinary(f'STOR {remote_path}', f)
                    logger.info(f"Uploaded file {file} to FTP")

                    if remove_files:
                        os.remove(local_path)
                        logger.info(f"Removed local file {file}")
                else:
                    logger.warning("File doesn't suit the specified regex structure")
                    not_matched.append(file)

            logger.info(f"Completed uploading list of files to FTP {self.hostname}")
            if not_matched:
                return not_matched

        except Exception as e:
            logger.error(f"Failed to upload list of files to FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def download_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                       close_conn: bool = False) -> Tuple[List[str], List[str]]:
        """
        Downloads files of a specified type from the FTP server.

        This method retrieves files from the remote directory (`self.remote`) on the FTP server that match the
        given `file_type`. The files are downloaded to the local directory (`self.get_f`). If `remove_files` is
        set to `True`, the files are deleted from the FTP server after successful download.

        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param remove_files: Optional; if `True`, deletes the files from the FTP server after download
                             (default is `False`).
        :type remove_files: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of downloaded files. If some files don't match the criteria, a tuple containing the
                 list of downloaded files and a list of non-matching files is returned.
        :rtype: list | tuple
        :raises Exception: If an error occurs during file download.
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started downloading files from FTP")
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
                        logger.info(f"Downloaded file {file} from FTP")

                        if remove_files:
                            ftp_conn.delete(file)
                            logger.info(f"Removed file {file} from FTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed downloading files from FTP {self.hostname}")
            if not_matched:
                return downloaded_files, not_matched
            return downloaded_files, []

        except Exception as e:
            logger.error(f"Failed to download files from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def get_file_sizes(self, file_type: str, logger_name: str, close_conn: bool = False) \
            -> Tuple[Dict[str, int], List[str]]:
        """
        Retrieves the sizes of files on the FTP server that match the specified type.

        This method identifies files on the FTP server within the remote directory (`self.remote`) that match the
        given `file_type`. For each matching file, it retrieves its size in bytes. Files that do not match the
        specified type or fail the optional regex validation are skipped and logged as warnings. The method
        returns a dictionary containing filenames as keys and their sizes in bytes as values. If there are
        unmatched files, a tuple containing the dictionary of file sizes and a list of unmatched files is returned.

        :param file_type: The type of files for which to retrieve sizes (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return:
            - If all files match the criteria, a dictionary with filenames as keys and their sizes in bytes as values.
            - If there are unmatched files, a tuple of the dictionary of file sizes and a list of unmatched files.
        :rtype: dict | tuple
        :raises Exception: If there is an error during file size retrieval.
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started reading file sizes on FTP")
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
                        logger.info(f"File size for {file} is {file_size} bytes")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed reading file sizes on FTP {self.hostname}")
            if not_matched:
                return file_sizes, not_matched
            return file_sizes, []

        except Exception as e:
            logger.error(f"Failed to read file sizes from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()

    @ftp_retry
    def download_out_of_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                   remove_files: bool = False, close_conn: bool = False) \
            -> Tuple[List[str], List[str]]:
        """
        Downloads files from the FTP server that match the given `file_type` and are NOT in the specified `files_list`.

        This method identifies files in the remote directory (`self.remote`) on the FTP server that match the
        specified `file_type` and are not present in the provided `files_list`. Matching files are downloaded
        to the local directory (`self.get_f`). If `remove_files` is `True`, the downloaded files are deleted
        from the remote directory.

        :param files_list: A list of filenames to exclude from the download. Files in this list will not be downloaded.
        :type files_list: list
        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param remove_files: If `True`, deletes the files from the FTP server after download (default is `False`).
        :type remove_files: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return:
            - A list of downloaded files.
            - If there are unmatched files, a tuple containing:
                - A list of downloaded files.
                - A list of unmatched files.
        :rtype: list | tuple
        :raises Exception: If there is an error during file download.
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started downloading files not in the specified list from FTP")
        downloaded_files = []
        try:
            ftp_conn = self.ftp
            files = ftp_conn.nlst(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file not in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, os.path.basename(file))
                        logger.info(f"Downloading file {file} from FTP")
                        with open(local_path, 'wb') as f:
                            ftp_conn.retrbinary(f'RETR {file}', f.write)
                        downloaded_files.append(file)
                        logger.info(f"Downloaded file {file} from FTP")

                        if remove_files:
                            ftp_conn.delete(file)
                            logger.info(f"Deleted file {file} from FTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed downloading files not in the specified list from FTP {self.hostname}")
            if not_matched:
                return downloaded_files, not_matched
            return downloaded_files, []

        except Exception as e:
            logger.error(f"Failed to download files not in the list from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()


    @ftp_retry
    def download_only_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                 remove_files: bool = False, close_conn: bool = False) \
            -> Tuple[List[str], List[str]]:
        """
        Downloads files from the FTP server that match the given `file_type` and are in the specified `files_list`.

        This method retrieves files from the remote directory (`self.remote`) on the SFTP server that match the
        specified `file_type` and are present in the provided `files_list`. Matching files are downloaded
        to the local directory (`self.get_f`). If `remove_files` is set to `True`, the downloaded files
        are deleted from the SFTP server after successful download.

        :param files_list: A list of filenames to download.
        :type files_list: list
        :param file_type: The type of files to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging the download process.
        :type logger_name: str
        :param remove_files: Optional; if `True`, deletes the files from the SFTP server after successful download.
                             Defaults to `False`.
        :type remove_files: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of successfully downloaded files. If any files do not match the regex or criteria, a tuple
                 (downloaded_files, unmatched_files) is returned.
        :rtype: list | tuple
        :raises Exception: If an error occurs during the download process.
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started downloading only specified files from FTP")
        downloaded_files = []
        try:
            ftp_conn = self.ftp
            files = ftp_conn.nlst(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, os.path.basename(file))
                        logger.info(f"Downloading file {file} from FTP")
                        with open(local_path, 'wb') as f:
                            ftp_conn.retrbinary(f'RETR {file}', f.write)
                        downloaded_files.append(file)
                        logger.info(f"Downloaded file {file} from FTP")

                        if remove_files:
                            ftp_conn.delete(file)
                            logger.info(f"Deleted file {file} from FTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed downloading only specified files from FTP {self.hostname}")
            if not_matched:
                return downloaded_files, not_matched
            return downloaded_files, []

        except Exception as e:
            logger.error(f"Failed to download specified files from FTP {self.hostname}: {e}")
            raise
        finally:
            if close_conn:
                self.close_connections()
