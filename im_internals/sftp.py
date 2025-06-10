import os
import re
import socket
import paramiko
import logging
from typing import List, Tuple, Dict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, before_sleep_log


# retry decorator for SFTP operations, using Tenacity
sftp_retry = retry(
    retry=retry_if_exception(lambda exc: isinstance(exc, (paramiko.SSHException, socket.error, IOError))),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=10),
    reraise=True,
    before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING)
)


class Sftp:
    """
    A class for interacting with SFTP servers, including file uploads, downloads, and remote file management.

    The `Sftp` class provides methods for establishing secure file transfer protocol (SFTP) connections, managing
    file transfers, and handling remote directories. It supports operations such as uploading, downloading, and
    logging activities for audit purposes.

    **Attributes**:
        - **hostname** (`str`): The hostname or IP address of the SFTP server.
        - **username** (`str`): The username for SFTP login.
        - **password** (`str`): The password for SFTP login.
        - **port** (`int`): The port number for the SFTP server (default: 22).
        - **files** (`str`): Local folder path containing the files to be processed.
        - **remote** (`str`): Remote folder path on the SFTP server.
        - **get_f** (`str`): Local folder path where downloaded files will be stored.
        - **log_folder** (`str`): Folder path where log files will be saved.
        - **_client** (`paramiko.SSHClient`): Internal SSH client for establishing SFTP connections.
        - **_sftp** (`paramiko.SFTPClient`): Internal SFTP client for file transfers.
        - **logger** (`logging.Logger`): Logger object for tracking operations.

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
    :param log_folder: Optional, the folder path where log files will be saved. If not specified,
                       logging will be disabled.
    :type log_folder: str, optional
    :param validation_regex: Regex that will be used for filtering the names of file or folders.
    :type validation_regex: str
    :param port: Optional, the port number for the SFTP connection (default is 22).
    :type port: int, optional
    """

    def __init__(self, hostname, username, password, files_folder, get_folder, remote_folder, log_folder,
                 log_name, validation_regex="", port=22):
        """
        Initializes the SFTP class with the given connection details, local and remote folder paths,
        and logging settings.

        This constructor sets up the SFTP connection details including the hostname, username, and password. It also
        initializes local and remote folder paths for file operations, sets up the logging directory, and creates
        placeholders for the SFTP client (`_client`) and SFTP session (`_sftp`).

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
        :param log_folder: The folder path where log files will be saved. If not specified, logging will be disabled.
        :type log_folder: str
        :param log_name: The folder file name where logs will be saved. If not specified, logging will be disabled.
        :type log_name: str
        :param validation_regex: Regex that will be used for filtering the names of file or folders.
        :type validation_regex: str
        :param port: Optional, the port number for the SFTP connection (default is 22).
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
        self.logger = None
        self._sftp = None
        self.val_regex = validation_regex

    def __del__(self):
        """
        Ensures all connections are closed when the instance is deleted.
        """
        self.close_connections()
        logging.info(f"SFTP connections for {self.hostname} have been closed upon deletion.")

    @property
    def client(self):
        """
        Establishes and returns the SSH client connection.

        If the SSH client is not already established, this property initializes the connection and logs in using the
        provided hostname, username, and password. This connection is required to initiate SFTP sessions.

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

        If the SFTP session is not already established, this property initializes the session using the SSH client.
        The SFTP session is used for file transfer operations, such as uploading, downloading, and managing
        remote files.

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

        This method ensures that both the SFTP session and SSH client are properly closed to free up resources and
        maintain a clean state. It sets the internal `_sftp` and `_client` attributes to `None`.
        """

        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def _log_setup(self, logger_name):
        """
        Sets up and returns a logger for tracking SFTP operations.

        This method initializes a logger object if it does not already exist. It configures the logger with a file
        handler to write logs to a specific log file, formats the log entries, and sets the logging level to `INFO`.
        This logging helps in tracking operations and errors for audit purposes.

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

    @sftp_retry
    def move_files(self, files_list: List[str], start_folder: str, end_folder: str, logger_name: str,
                   close_conn: bool = False) -> None | List[str]:
        """
        Moves files from one folder to another on the SFTP server.

        This method renames files on the SFTP server, effectively moving them from the `start_folder`
        to the `end_folder`.
        If `files_list` is empty, all files in the `start_folder` are retrieved. Only `.pdf` files matching an optional
        regex (`val_regex`) are moved. Files that do not match the regex are returned in a list.

        :param files_list: List of filenames to move. If empty, all files in `start_folder` will be processed.
        :type files_list: list
        :param start_folder: The remote folder path on the SFTP server containing the files to be moved.
        :type start_folder: str
        :param end_folder: The remote folder path on the SFTP server where the files will be moved.
        :type end_folder: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of files that did not match the regex (if any), otherwise `None`.
        :rtype: None | list
        :raises Exception: If an error occurs during the file move operation.
        """
        assert isinstance(files_list, list), "Files list must be a list only with the filenames (No PATHS included)!"
        assert isinstance(start_folder, str) and "/" in start_folder, \
            "Remote folder must be a path string and it must contains '/' as SFTP path should be 'Folder/File'"
        assert isinstance(end_folder, str) and "/" in end_folder, \
            "Remote folder must be a path string and it must contains '/' as SFTP path should be 'Folder/File'"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started moving files to SFTP")
        try:
            if not files_list:
                files_list = self.sftp.listdir(start_folder)

            for file in files_list:
                if file.lower().endswith(".pdf"):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        logger.info(f"Started moving file {file} to SFTP")
                        old_file_path = os.path.join(start_folder, file)
                        new_file_path = os.path.join(end_folder, file)
                        self.sftp.rename(oldpath=old_file_path, newpath=new_file_path)
                        logger.info(f"Moved file {file} to folder {end_folder}")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed moving files to folder {end_folder}")
            if not_matched:
                return not_matched

        except (Exception, socket.error) as e:
            logger.error(f"Error moving files from {start_folder} to {end_folder} on SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def upload_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                     close_conn: bool = False) -> None | List[str]:
        """
        Uploads files of a specific type from a local folder to the SFTP server.

        This method uploads files from the local directory (`self.files`) to the remote directory (`self.remote`) on the
        SFTP server. Only files matching the specified `file_type` are considered for upload. Optionally, local files
        can be removed after successful upload by setting `remove_files=True`. Files that do not match an optional regex
        (`val_regex`) are skipped and returned in a list.

        :param file_type: The type of files to upload (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param remove_files: Optional; if `True`, deletes the local files after successful upload. Defaults to `False`.
        :type remove_files: bool
        :return: A list of files that did not match the regex (if any), otherwise `None`.
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :rtype: None | list
        :raises Exception: If an error occurs during the file upload.
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started uploading files to SFTP")
        try:
            for dirpath, _, filenames in os.walk(self.files):
                for file in filenames:
                    if file.lower().endswith(file_type.lower()):
                        filename = file[:file.rfind(".")]
                        if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                            local_path = os.path.join(dirpath, file)
                            remote_path = self.remote + f"/{file}"
                            self.sftp.put(localpath=local_path, remotepath=remote_path)
                            logger.info(f"Uploaded file {file} to SFTP")

                            if remove_files:
                                os.remove(local_path)
                                logger.info(f"Removed local file {file}")
                        else:
                            logger.warning("File doesn't suit the specified regex structure")
                            not_matched.append(file)

                logger.info(f"Completed uploading files to the SFTP {self.hostname}")
                if not_matched:
                    return not_matched

        except (Exception, socket.error) as e:
            logger.error(f"Error uploading files to SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
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
        logger.info("Started uploading list of files to SFTP")
        try:
            for file in files_list:
                filename = file[:file.rfind(".")]
                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                    local_path = os.path.join(self.files, file)
                    remote_path = self.remote + f"/{file}"
                    logger.info(f"Uploading file {file} to SFTP")
                    self.sftp.put(localpath=local_path, remotepath=remote_path)
                    logger.info(f"Uploaded file {file} to SFTP")

                    if remove_files:
                        os.remove(local_path)
                        logger.info(f"Removed local file {file}")
                else:
                    logger.warning("File doesn't suit the specified regex structure")
                    not_matched.append(file)

            logger.info(f"Completed uploading files to the SFTP {self.hostname}")
            if not_matched:
                return not_matched

        except (Exception, socket.error) as e:
            logger.error(f"Failed to upload files to SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def download_files(self, file_type: str, logger_name: str, remove_files: bool = False,
                       close_conn: bool = False) -> Tuple[List[str], List[str]]:
        """
        Downloads files of a specified type from the SFTP server.

        This method downloads files from the remote directory (`self.remote`) on the SFTP server that match the
        specified `file_type`. The downloaded files are saved in the local directory (`self.get_f`).
        If `remove_files` is set to `True`, the files are deleted from the remote directory after
        they are successfully downloaded. The method returns a list of successfully downloaded files. If any
        files do not match the specified regex or criteria, they are added to a separate list of unmatched files.

        :param file_type: The file extension/type to download (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging the download process.
        :type logger_name: str
        :param remove_files: Optional; if `True`, deletes the files from the SFTP server after download.
               Defaults to `False`.
        :type remove_files: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A list of downloaded files. If there are unmatched files, a tuple of
                 downloaded and unmatched files is returned.
        :rtype: list | tuple
        :raises Exception: If an error occurs during the download process.
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(remove_files, bool), "Remove_files must be either True/False to remove local files!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []

        logger = self._log_setup(logger_name)
        logger.info("Started downloading files from SFTP")
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
                        logger.info(f"Downloaded file {file} from SFTP")
                        downloaded_files.append(file)

                        if remove_files:
                            self.sftp.remove(remote_path)
                            logger.info(f"Removed file {file} from SFTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed downloading files from SFTP {self.hostname}")
            if not_matched:
                return downloaded_files, not_matched
            return downloaded_files, []

        except (Exception, socket.error) as e:
            logger.error(f"Error downloading files from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def download_out_of_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                   remove_files: bool = False, close_conn: bool = False) -> Tuple[List[str], List[str]]:
        """
        Downloads files from the SFTP server that match the given `file_type` and are NOT in the specified `files_list`.

        This method retrieves files from the remote directory (`self.remote`) on the SFTP server that match the
        specified `file_type` and are not present in the provided `files_list`. Matching files are downloaded
        to the local directory (`self.get_f`). If `remove_files` is set to `True`, the downloaded files are
        removed from the SFTP server after successful download. The method returns a list of downloaded files,
        or a tuple containing downloaded and unmatched files if any files do not meet the regex or other criteria.

        :param files_list: A list of filenames to exclude from the download.
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
        :return: A list of downloaded files. If any files do not match, a tuple of
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
        logger.info("Started downloading files not in the given list from SFTP")
        downloaded_files = []
        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file not in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, file)
                        remote_path = self.remote + f"/{file}"
                        logger.info(f"Downloading file {file} from SFTP")
                        self.sftp.get(localpath=local_path, remotepath=remote_path)
                        downloaded_files.append(file)
                        logger.info(f"Downloaded file {file} from SFTP")

                        if remove_files:
                            self.sftp.remove(remote_path)
                            logger.info(f"Removed file {file} from SFTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed downloading files not in the given list from SFTP {self.hostname}")
            if not_matched:
                return downloaded_files, not_matched
            return downloaded_files, []

        except (Exception, socket.error) as e:
            logger.error(f"Failed to download files from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def download_only_list_files(self, files_list: List[str], file_type: str, logger_name: str,
                                 remove_files: bool = False, close_conn: bool = False) \
            -> Tuple[List[str], List[str]]:
        """
        Downloads files from the SFTP server that match the given `file_type` and are in the specified `files_list`.

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
        logger.info("Started downloading only specified files from SFTP")
        downloaded_files = []
        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()) and file in files_list:
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        local_path = os.path.join(self.get_f, file)
                        remote_path = self.remote + f"/{file}"
                        logger.info(f"Downloading file {file} from SFTP")
                        self.sftp.get(localpath=local_path, remotepath=remote_path)
                        downloaded_files.append(file)
                        logger.info(f"Downloaded file {file} from SFTP")

                        if remove_files:
                            self.sftp.remove(remote_path)
                            logger.info(f"Removed file {file} from SFTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed downloading specified files from SFTP {self.hostname}")
            if not_matched:
                return downloaded_files, not_matched
            return downloaded_files, []

        except (Exception, socket.error) as e:
            logger.error(f"Failed to download files from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()

    @sftp_retry
    def get_files_sizes(self, file_type: str, logger_name: str, close_conn: bool = False) \
            -> Tuple[Dict[str, int], List[str]]:
        """
        Retrieves the sizes of files on the SFTP server that match the specified type.

        This method scans the remote directory (`self.remote`) on the SFTP server and retrieves the sizes (in bytes)
        of files that match the given `file_type`. The file sizes are returned as a dictionary, with filenames as keys
        and their sizes in bytes as values. Files that do not match the specified regex (if provided) are
        logged separately.

        :param file_type: The type of files to retrieve sizes for (e.g., '.txt', '.pdf').
        :type file_type: str
        :param logger_name: The name of the logger to use for logging operations.
        :type logger_name: str
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :return: A dictionary containing filenames as keys and their sizes (in bytes) as values.
                 If some files do not match
                 the specified regex, a tuple is returned, with the dictionary of sizes and a list of unmatched files.
        :rtype: dict | tuple
        :raises Exception: If there is an error during file size retrieval or communication with the SFTP server.
        """
        assert isinstance(file_type, str), "File type must be a string!"
        assert isinstance(logger_name, str), "Logger name must be a string!"
        assert isinstance(close_conn, bool), "Close_conn must be either True or False"

        not_matched = []
        logger = self._log_setup(logger_name)
        logger.info("Started reading file sizes on SFTP")
        file_sizes = {}

        try:
            files = self.sftp.listdir(self.remote)
            for file in files:
                if file.lower().endswith(file_type.lower()):
                    filename = file[:file.rfind(".")]
                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                        remote_path = self.remote + f"/{file}"
                        file_sizes[file] = self.sftp.stat(remote_path).st_size
                        logger.info(f"Read file size for {file} from SFTP")
                    else:
                        logger.warning("File doesn't suit the specified regex structure")
                        not_matched.append(file)

            logger.info(f"Completed reading file sizes from SFTP {self.hostname}")
            if not_matched:
                return file_sizes, not_matched
            return file_sizes, []

        except (Exception, socket.error) as e:
            logger.error(f"Failed to read file sizes from SFTP {self.hostname}: {e}")
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

        :param filename: Name of the file (including extension) on the SFTP server to verify.
                         Must contain a “.” to separate name and extension.
        :type filename: str
        :param chunk_size: Number of bytes to hash at each end of the file. Must be a positive integer
                           strictly less than half the total file size.
        :type chunk_size: int
        :param first_local_md5_chunk: The MD5 digest (16-byte binary) of the **first** `chunk_size`
                                      bytes of the local file.
        :type first_local_md5_chunk: bytes
        :param last_local_md5_chunk: The MD5 digest (16-byte binary) of the **last** `chunk_size`
                                     bytes of the local file.
        :type last_local_md5_chunk: bytes
        :param logger_name: Name for the logger; used to emit info / error messages at each step.
        :type logger_name: str
        :return: **True** if *both* the remote first-chunk MD5 and last-chunk MD5 exactly match the provided
                 local MD5 digests.
        :rtype: bool
        :param close_conn: Optional, if True, after completing the process, closes all open connections
        :type close_conn: bool
        :raises AssertionError: If `filename` isn’t a non-empty string containing an extension,
                                or if `chunk_size` is not a positive integer.
        :raises IOError: If the remote file object is not seekable (so its size or chunks can’t be read).
        :raises Exception: Propagates any underlying SFTP or I/O errors (connection issues, permissions, etc.).
        """
        logger = self._log_setup(logger_name)
        logger.info("Started file hash verification.")

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
            logger.info(f"Changed path to {self.remote}")

            with self.sftp.open(filename=filename, mode="r") as sftp_file:
                if sftp_file.seekable():
                    first_data_chunk = sftp_file.read(chunk_size)
                    file_size = sftp_file.stat().st_size
                    logger.info("ZIP file size: %i", file_size)
                    sftp_file.seek(file_size - chunk_size)
                    last_data_chunk = sftp_file.read(chunk_size)
                    logging.info("Prepared remote data chunks: \nFirst => %s\nLast => %s",
                                 first_data_chunk, last_data_chunk)
                else:
                    raise IOError("File is not Seekable to verify its HASH!!Verify file path and file completeness")

            logger.info(f"Completed verifying file MD5 hash")
            return first_data_chunk == first_local_md5_chunk and last_data_chunk == last_local_md5_chunk

        except (Exception, socket.error) as e:
            logger.error(f"Failed to read file sizes from SFTP {self.hostname}: {e}")
            raise

        finally:
            if close_conn:
                self.close_connections()
