from pathlib import Path
import logging
from im_internals.sanitize import sanitize_string


class Folder:
    """
    Utility class for managing and sanitizing filesystem folders.

    :param path: Path to the target folder.
    """
    def __init__(self, folder_path: str):
        """
        Initialize Folder object for the given folder path.

        :param path: Absolute or relative path to the folder.
        :raises FileNotFoundError: If the folder does not exist.
        :raises OSError: If the path cannot be resolved.
        """
        try:
            self.path = Path(folder_path).resolve()
            if not self.path.exists() or not self.path.is_dir():
                raise FileNotFoundError(f"{self.path} does not exist or is not a directory")
            self.parent = self.path.parent
            self.name = self.path.name
        except Exception as e:
            logging.error(f"Error initializing Folder for {folder_path}: {e}")
            raise

    @property
    def full_path(self) -> str:
        """
        Return the absolute path of the folder.

        :returns: Full absolute path as a string.
        """
        return str(self.path)

    def sanitize_name(self) -> str:
        """
        Generate a sanitized version of the folder name using sanitize_string().

        :returns: Sanitized folder name.
        """
        try:
            return sanitize_string(self.name)
        except Exception as e:
            logging.error(f"Error sanitizing folder name for {self.path}: {e}")
            raise

    def sanitize(self) -> str:
        """
        Rename the folder on disk if its name contains disallowed characters.

        :returns: The updated folder name.
        :raises OSError: If the folder cannot be renamed.
        """
        sanitized = self.sanitize_name()
        if sanitized != self.name:
            new_path = self.parent / sanitized
            try:
                self.path.rename(new_path)
                logging.info(f"Renamed folder '{self.name}' → '{sanitized}'")
                self.path = new_path
                self.name = sanitized
            except Exception as e:
                logging.error(f"Failed to rename folder '{self.name}' to '{sanitized}': {e}")
                raise
        return self.name
