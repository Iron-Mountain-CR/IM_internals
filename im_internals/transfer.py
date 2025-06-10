import os
import re
import shutil
import logging
import socket
import inspect
from im_internals.file import File
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

# Logger for retry events
logger = logging.getLogger(__name__)


# retry on transient FS errors with exponential backoff
retry_file_ops = retry(
    retry=retry_if_exception_type((FileNotFoundError, PermissionError, socket.error)),
    stop=stop_after_attempt(5),
    reraise=True,
    wait=wait_exponential(multiplier=1, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)


@retry_file_ops
def robust_move(src: str, dst: str) -> None:
    """Move, retrying on transient errors."""
    shutil.move(src, dst)


@retry_file_ops
def robust_copy(src: str, dst: str) -> None:
    """Copy (with metadata), retrying on transient errors."""
    shutil.copy2(src, dst)


@retry_file_ops
def robust_copytree(src: str, dst: str, **kwargs) -> None:
    """
    Recursively copy a directory tree from src to dst, retrying on transient errors.
    Accepts the same kwargs as shutil.copytree, e.g., dirs_exist_ok.
    """
    shutil.copytree(src, dst, **kwargs)


def get_unique_filename(dest_path, file):
    """
    Generate a unique filename if the file already exists in the destination folder.
    """
    filename, ext = file[:file.rfind(".")], file[file.rfind("."):]
    counter = 1
    new_filename = file

    while os.path.exists(os.path.join(dest_path, new_filename)):
        new_filename = f"{filename}_{counter}{ext}"
        counter += 1

    return new_filename


def recursive_folder_lookup(src_path: str, dest_path: str, list_names: list, not_matched: list,
                            origin_path: str, val_regex: str):
    """
    Recursively searches for folders and files in a source directory and copies them to a destination directory.

    :param str src_path: The source directory path.
    :param str dest_path: The destination directory path.
    :param list list_names: A list to store the names of the copied files.
    :param list not_matched: A list to store the names of folders that did not match the regex filter.
    :param str origin_path: The original source directory path for reference in recursive operations.
    :param str val_regex: A regex pattern used for validating the naming of folders.

    This function traverses the source directory (`src_path`) recursively. For each folder in the source directory,
    it creates a corresponding folder in the destination directory (`dest_path`) if it doesn't already exist. Then,
    it recursively calls itself to traverse subfolders. For each file found, it copies the file to the corresponding
    location in the destination directory.

    Folders that do not match the specified regex pattern are added to `not_matched` instead of being copied.
    Successfully copied files are appended to `list_names`.
    """
    folders = os.listdir(src_path)
    for folder in folders:
        os.chdir(src_path)
        if os.path.isdir(folder):
            if not val_regex or re.fullmatch(val_regex, folder):
                logging.info(f"Found a folder in {src_path}")
                try:
                    logging.info(f"Trying to create a folder in {dest_path}")
                    os.chdir(dest_path)
                    os.mkdir(folder)
                    logging.info("Completed creaition of the folder")
                except FileExistsError:
                    logging.info(f"Folder already exist in {dest_path}")
                    pass
                recursive_folder_lookup(src_path=src_path+f"\\{folder}", dest_path=dest_path+f"\\{folder}",
                                        list_names=list_names, not_matched=not_matched,
                                        origin_path=origin_path, val_regex=val_regex)
            else:
                logging.warning("Folder doesn't suit the specified regex structure")
                not_matched.append(folder)

        elif src_path != origin_path:
            file = folder
            old_file = File(src_path, file)
            if (os.path.exists(os.path.join(dest_path, file))
                    and old_file.md_hash == File(dest_path, file).md_hash):
                logging.info(f"File {file} already exists in the {dest_path}")
                continue

            logging.info(f"Started copying file {file} from {src_path} to {dest_path}")
            robust_copy(src_path+f"\\{file}", dest_path+f"\\{file}")
            list_names.append(file)
            logging.info("Completed copying the file")


def move_folder_content(src, dest):
    """
    Recursively moves the contents from the source directory (`src`) to the destination directory (`dest`).
    If subdirectories exist, it continues moving them recursively. Existing files in `dest` are overwritten.

    :param str src: The source directory from which to move content.
    :param str dest: The destination directory to which content is moved.

    Creates the `dest` directory if it does not exist. For each item in `src`, moves it to `dest`.
    If an item in `dest` is a directory and has the same name as one in `src`, the function recurses into it.
    """
    if not os.path.exists(dest):
        os.makedirs(dest)
        logging.info(f"Created folder: {dest}")

    for item in os.listdir(src):
        src_item = os.path.join(src, item)
        dest_item = os.path.join(dest, item)

        if os.path.exists(dest_item):
            if os.path.isdir(dest_item) and os.path.isdir(src_item):
                logging.info(f"Started moving files in subfolder: {dest_item.split('\\')[-1]}")
                move_folder_content(src_item, dest_item)
            else:
                new_dest_item = get_unique_filename(dest, item)
                robust_move(src_item, os.path.join(dest, new_dest_item))
                logging.info(f"Renamed and moved File: {new_dest_item}")
        else:
            robust_move(src_item, dest_item)
            logging.info(f"Moved File: {dest_item.split('\\')[-1]}")


class Move:
    def __init__(self, temp_folder: str, archive_folder: str, files_folder: str, validation_regex=""):
        """
        Initialization of the Class.
        :param str temp_folder: Folder which will be used as temp folder. Further will be named as TF
        :param str archive_folder: Folder which will be used as archive folder. Further will be named as AF
        :param str files_folder: Folder which will be used as files folder. Further will be named as FF
        :param str validation_regex: Regex that will be used for filtering the names of file or folders.
        """
        self.temp = temp_folder
        self.archive = archive_folder
        self.real_files = files_folder
        self.from_path = None
        self.to_path = None
        self.val_regex = validation_regex

    @property
    def from_ff(self):
        self.from_path = self.real_files
        return self

    @property
    def from_tf(self):
        self.from_path = self.temp
        return self

    @property
    def from_af(self):
        self.from_path = self.archive
        return self

    def from_f(self, folder_path: str):
        if folder_path != "":
            self.from_path = folder_path
            return self
        else:
            raise ValueError("Folder path can't be empty String!!!")

    @property
    def to_ff(self):
        self.to_path = self.real_files
        return self

    @property
    def to_tf(self):
        self.to_path = self.temp
        return self

    @property
    def to_af(self):
        self.to_path = self.archive
        return self

    def to_f(self, folder_path: str):
        if folder_path != "":
            self.to_path = folder_path
            return self
        else:
            raise ValueError("Folder path can't be empty String!!!")

    @property
    def get_method_name(self):
        return inspect.currentframe().f_back.f_code.co_name

    def move_files_or_folders(self, file_type: str, logger_name: str, save_paths: bool,
                              move_folder=False) -> tuple | list:
        """
        Moves files or folders from one location to another based on the specified file type or folder structure.

        :param str file_type: The type of files to move (e.g., ".txt", ".pdf").
        :param str logger_name: Logger name for logging operations.
        :param bool save_paths: If True, retains the set paths after execution.
        :param bool move_folder: If True, moves folders instead of individual files.
        :return: A list of moved files or folders, or a tuple with non-matching files or folders when regex is applied.

        Moves files from `from_path` to `to_path` based on `file_type`. Uses `val_regex` for additional filtering.
        Logs progress. If paths are not set, raises ValueError.

        If move_folder is False (default), the method moves individual files with the specified file type from
        from_path to to_path. If move_folder is True, the method moves entire folders from from_path to to_path.

        After successfully moving files or folders, the method returns a list of the moved files or folders.

        If the from_path or to_path is not specified, the method raises a ValueError.

        Any call to this method should be preceded by setting from_path and to_path using the from_XXXX and to_XXXX
        methods. For example: Move.from_XXX.to_XXX.move_files_or_folders("txt", "example_logger")

        """
        moved_files, not_matched = [], []
        low_type = str.lower(file_type)
        up_type = str.upper(file_type)
        logger = logging.getLogger(logger_name)

        if self.from_path and self.to_path:
            if not move_folder:
                logger.info(f"Started moving {up_type} files from {self.from_path} to Temp in {self.to_path}")
                try:
                    for file in os.listdir(self.from_path):
                        if not os.path.isdir(os.path.join(self.from_path, file)):
                            if file.endswith(low_type) or file.endswith(up_type):
                                filename = file[:file.rfind(".")]
                                logger.info(f"Verifying file: {filename}")
                                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                                    logger.info("Verified")
                                    dest_file = get_unique_filename(self.to_path, file)
                                    moved_files.append(dest_file)
                                    logger.info(f"Started moving {up_type} file {dest_file}")
                                    robust_move(self.from_path + f"\\{file}", self.to_path + f"\\{dest_file}")
                                    logger.info(f"Completed moving {up_type} file {dest_file}")
                                else:
                                    logger.warning("File doesn't suit the specified regex structure")
                                    not_matched.append(file)
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send {up_type} file to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving {up_type} files to {self.to_path} folder.")

            else:
                logger.info(f"Started moving folders from {self.from_path} to {self.to_path}")
                try:
                    folders = os.listdir(self.from_path)
                    for folder in folders:
                        if os.path.isdir(os.path.join(self.from_path, folder)):
                            if self.val_regex == "" or re.fullmatch(self.val_regex, folder):
                                moved_files.append(folder)
                                logger.info(f"Started moving folder {folder}")
                                src_path = self.from_path + f"\\{folder}"
                                dest_path = self.to_path + f"\\{folder}"
                                move_folder_content(src_path, dest_path)
                                logger.info(f"Completed moving folder {folder}")
                            else:
                                logger.warning("Folder doesn't suit the specified regex structure")
                                not_matched.append(folder)
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send folders to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving folders to {self.to_path} folder.")

            if not save_paths:
                self.from_path = None
                self.to_path = None

            if not_matched:
                return moved_files, not_matched
            return moved_files

        else:
            if not self.from_path:
                raise ValueError(f"From path wasn't specified!!!. Please use one of the from_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")
            if not self.to_path:
                raise ValueError(f"To path wasn't specified!!!. Please use one of the to_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")

    def move_list_of_files_or_folder(self, list_of_names: list, logger_name: str, save_folders: bool,
                                     move_folder=False) -> list | None:
        """
        Moves specified files or folders from one location to another.

        :param list list_of_names: Names of files or folders to move.
        :param str logger_name: Logger name for logging.
        :param bool save_folders: If True, retains the set paths after execution.
        :param bool move_folder: If True, moves folders instead of files.
        :return: `not_matched` list if regex filtering is applied; otherwise, returns None.

        Moves files listed in `list_of_names` from `from_path` to `to_path`. Filters names using `val_regex` if specified.
        Raises ValueError if paths are not set.

        If move_folder is False (default), the method moves individual files specified in the list_of_names from
        from_path to to_path. If move_folder is True, the method moves entire folders specified in the list_of_names
        from from_path to to_path using robust_move.

        If the from_path or to_path is not specified, the method raises a ValueError.

        Any call to this method should be preceded by setting from_path and to_path using the from_XXXX and to_XXXX
        methods. For example: Move.from_XXX.to_XXX.move_list_of_files_or_folder(["file1.txt", "file2.txt"],
        "example_logger")

        """
        not_matched = []
        logger = logging.getLogger(logger_name)

        if self.from_path and self.to_path:
            if not move_folder:
                logger.info(f"Started moving files from {self.from_path} to Temp in {self.to_path}")
                try:
                    for dirpath, dirnames, filenames in os.walk(self.from_path):
                        for file in filenames:
                            for list_file in list_of_names:
                                if list_file == file:
                                    filename = file[:file.rfind(".")]
                                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                                        logger.info("Verification status: VALID")
                                        dest_file = get_unique_filename(self.to_path, file)
                                        logger.info(f"Started moving file {dest_file}")
                                        robust_move(dirpath + f"\\{file}", self.to_path + f"\\{dest_file}")
                                        logger.info(f"Completed moving file {dest_file}")
                                        break
                                    else:
                                        logger.warning("File doesn't suit the specified regex structure")
                                        not_matched.append(file)
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send file to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving files to {self.to_path} folder.")

            else:
                logger.info(f"Started moving folders from {self.from_path} to {self.to_path}")
                try:
                    folders = os.listdir(self.from_path)
                    for folder in folders:
                        if os.path.isdir(os.path.join(self.from_path, folder)) and folder in list_of_names:
                            if self.val_regex == "" or re.fullmatch(self.val_regex, folder):
                                logger.info(f"Started moving folder {folder}")
                                src_path = self.from_path + f"\\{folder}"
                                dest_path = self.to_path + f"\\{folder}"
                                move_folder_content(src_path, dest_path)
                                logger.info(f"Completed moving folder {folder}")
                            else:
                                logger.warning("Folder doesn't suit the specified regex structure")
                                not_matched.append(folder)
                        elif folder in list_of_names and not os.path.isdir(os.path.join(self.from_path, folder)):
                            raise FileNotFoundError(f"Folder with the name: '{folder}' doesn't exist in the "
                                                    f"path: {self.from_path}")
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send folders to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving folders to {self.to_path} folder.")

            if not save_folders:
                self.from_path = None
                self.to_path = None

            if self.val_regex:
                return not_matched

        else:
            if not self.from_path:
                raise ValueError(f"From path wasn't specified!!!. Please use one of the from_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")
            if not self.to_path:
                raise ValueError(f"To path wasn't specified!!!. Please use one of the to_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")

    def copy_files_or_folders(self, file_type: str, logger_name: str, save_folders: bool,
                              move_folder=False) -> tuple | list:
        """
        Copies files or folders from one location to another based on specified file type or folder structure.

        :param str file_type: The type of files to copy (e.g., ".txt", ".pdf").
        :param str logger_name: Logger name for logging operations.
        :param bool save_folders: If True, retains the set paths after execution.
        :param bool move_folder: If True, copies folders instead of individual files.
        :return: A list of copied files or folders, or a tuple with non-matching files or folders if regex is applied.

        Copies files from `from_path` to `to_path` based on `file_type`. Filters using `val_regex` if specified.
        Raises ValueError if paths are not set.

        If move_folder is False (default), the method copies individual files with the specified file type from
        from_path to to_path. If move_folder is True, the method recursively copies entire folders from from_path to
        to_path using a custom function `recursive_folder_lookup`.

        After successfully copying files or folders, the method returns a list of the copied files or folders.

        If the from_path or to_path is not specified, the method raises a ValueError.

        Any call to this method should be preceded by setting from_path and to_path using the from_XXXX and to_XXXX
        methods. For example: Move.from_XXX.to_XXX.copy_files_or_folders("txt", "example_logger")

        """
        copy_files, not_matched = [], []
        low_type = str.lower(file_type)
        up_type = str.upper(file_type)
        logger = logging.getLogger(logger_name)

        if self.from_path and self.to_path:
            if move_folder is False:
                logger.info(f"Started moving {up_type} files from {self.from_path} to {self.to_path}")
                try:
                    for file in os.listdir(self.from_path):
                        if not os.path.isdir(os.path.join(self.from_path, file)):
                            if file.endswith(low_type) or file.endswith(up_type):
                                filename = file[:file.rfind(".")]
                                if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                                    copy_files.append(file)
                                    old_file = File(self.from_path, file)

                                    if (os.path.exists(os.path.join(self.to_path, file))
                                            and old_file.md_hash == File(self.to_path, file).md_hash):
                                        logger.info(f"File {file} already exists in the {self.to_path}")
                                        continue

                                    logger.info(f"Started moving {up_type} file {file}")
                                    robust_copy(self.from_path + f"\\{file}", self.to_path + f"\\{file}")
                                    logger.info(f"Completed moving {up_type} file {file}")
                                else:
                                    logger.warning("File doesn't suit the specified regex structure")
                                    not_matched.append(file)
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send {up_type} file to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving {up_type} files to {self.to_path} folder.")

            elif move_folder is True:
                logger.info(f"Started moving folders from {self.from_path} to archive in {self.to_path}")
                try:
                    logger.info("Started recursive folder lookup")
                    recursive_folder_lookup(self.from_path, self.to_path, copy_files, not_matched, self.from_path,
                                            self.val_regex)
                    logger.info("Completed recursive folder lookup")
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send folder to {self.to_path} folder!!")
                    logger.exception("debug")
                    raise
                logger.info(f"Completed moving folders to {self.to_path} folder.")

            if not save_folders:
                self.from_path = None
                self.to_path = None

            if not_matched:
                return copy_files, not_matched
            return copy_files

        else:
            if not self.from_path:
                raise ValueError(f"From path wasn't specified!!!. Please use one of the from_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")
            if not self.to_path:
                raise ValueError(f"To path wasn't specified!!!. Please use one of the to_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")

    def copy_list_of_files_or_folders(self, list_of_names: list, logger_name: str, save_folders: bool,
                                      move_folder=False) -> list | None:
        """
        Copies specified files or folders from one location to another.

        :param list list_of_names: Names of files or folders to copy.
        :param str logger_name: Logger name for logging.
        :param bool save_folders: If True, retains the set paths after execution.
        :param bool move_folder: If True, copies folders instead of files.
        :return: `not_matched` list if regex filtering is applied; otherwise, returns None.

        Copies files or folders listed in `list_of_names` from `from_path` to `to_path`. Filters names using `val_regex`.
        Raises ValueError if paths are not set.

        If move_folder is False (default), the method copies individual files specified in the list_of_names from
        from_path to to_path. If move_folder is True, the method copies entire folders specified in the list_of_names
        from from_path to to_path using robust_copytree.

        If the from_path or to_path is not specified, the method raises a ValueError.

        Any call to this method should be preceded by setting from_path and to_path using the from_XXXX and to_XXXX
        methods. For example: Move.from_XXX.to_XXX.copy_list_of_files_or_folders()

        """
        not_matched = []
        logger = logging.getLogger(logger_name)

        if self.from_path and self.to_path:
            if not move_folder:
                logger.info(f"Started moving files from {self.from_path} to Temp in {self.to_path}")
                try:
                    for dirpath, dirnames, filenames in os.walk(self.from_path):
                        for file in filenames:
                            for list_file in list_of_names:
                                if list_file == file:
                                    filename = file[:file.rfind(".")]
                                    print(self.val_regex)
                                    if self.val_regex == "" or re.fullmatch(self.val_regex, filename):
                                        old_file = File(self.from_path, file)

                                        if (os.path.exists(os.path.join(self.to_path, file))
                                                and old_file.md_hash == File(self.to_path, file).md_hash):
                                            logger.info(f"File {file} already exists in the {self.to_path}")
                                            continue

                                        logger.info(f"Started moving file {file}")
                                        robust_copy(dirpath + f"\\{file}", self.to_path + f"\\{file}")
                                        logger.info(f"Completed moving file {file}")
                                        break
                                    else:
                                        logger.warning("File doesn't suit the specified regex structure")
                                        not_matched.append(file)
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send file to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving files to {self.to_path} folder.")

            else:
                logger.info(f"Started moving folders from {self.from_path} to {self.to_path}")
                try:
                    folders = os.listdir(self.from_path)
                    for folder in folders:
                        if os.path.isdir(os.path.join(self.from_path, folder)) and folder in list_of_names:
                            if self.val_regex == "" or re.fullmatch(self.val_regex, folder):
                                logger.info(f"Started moving folder {folder}")
                                robust_copytree(self.from_path + f"\\{folder}", self.to_path + f"\\{folder}",
                                                dirs_exist_ok=True)
                                logger.info(f"Completed moving folder {folder}")
                            else:
                                logger.warning("Folder doesn't suit the specified regex structure")
                                not_matched.append(folder)
                        elif folder in list_of_names and not os.path.isdir(os.path.join(self.from_path, folder)):
                            raise FileNotFoundError(f"Folder with the name: '{folder}' doesn't exist in the "
                                                    f"path: {self.from_path}")
                except (FileNotFoundError, Exception, socket.error):
                    logger.error(f"Wasn't able to send folders to {self.to_path} folder!!")
                    logger.exception("DEBUG")
                    raise
                logger.info(f"Completed moving folders to {self.to_path} folder.")

            if not save_folders:
                self.from_path = None
                self.to_path = None

            if self.val_regex:
                return not_matched

        else:
            if not self.from_path:
                raise ValueError(f"From path wasn't specified!!!. Please use one of the from_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")
            if not self.to_path:
                raise ValueError(f"To path wasn't specified!!!. Please use one of the to_XXXX methods! Any call "
                                 f"should look like this: Move.from_XXX.to_XXX.{self.get_method_name}()")
