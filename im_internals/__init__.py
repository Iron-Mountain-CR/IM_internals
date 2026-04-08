"""
im_internals package
Bundled helpers for database access, (S)FTP/file transfer, REST APIs,
e-mail sending/processing, and assorted utilities, for internal use only.
"""


from importlib import import_module as _mod
from importlib.metadata import version, PackageNotFoundError

__all__ = [
    "api",
    "cfg_commands",
    "email",
    "file",
    "folder",
    "ftp",
    "logging",
    "sanitize",
    "sftp",
    "sql",
    "transfer",
]

# Lazy-import the sub-modules so startup remains fast
for _name in __all__:
    globals()[_name] = _mod(f".{_name}", __name__)

try:
    __version__ = version("im_internals")
except PackageNotFoundError:
    __version__ = "unknown"


