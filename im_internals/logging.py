"""
Logging
===========
Centralised logging for all scripts.

Usage in an entry-point script::

    import im_internals.project_logging as pl
    pl.configure(
        name="PROJECT-IMPORT",
        log_file="process_import_files_20251204.log",
    )

All helper modules that need to log simply do::

    from im_internals import project_logging as pl
    pl.progress("...")
    pl.warn("...")
    pl.error("...")

The module-level convenience functions delegate to the single configured
instance, so no logger object needs to be threaded through function arguments.

Configuring a custom format string::

    pl.configure(
        name="PROJECT-IMPORT",
        log_file="...",
        fmt="%(name)s %(asctime)s | %(funcName)s | %(lineno)d - %(message)s",
    )
"""
import datetime
import logging
import time
import traceback
from contextlib import contextmanager
from typing import Optional

# ── default format ────────────────────────────────────────────────────────────
DEFAULT_FMT = "%(name)s %(asctime)s| %(funcName)s| %(lineno)d - %(message)s"
DEFAULT_DATEFMT = "%d-%m-%y %H:%M:%S"


# ── logger class ──────────────────────────────────────────────────────────────
class Logger:
    """
    Logging wrapper for scripts.

    Combines structured stdout output (with timestamp and script name prefix)
    with Python's standard logging to a file.

    Parameters
    ----------
    name : str
        Label used in every stdout line, e.g. ``"PROJECT-IMPORT"``.
        Also used as the Python logger name (``logging.getLogger(name)``).
    log_file : str
        Path to the log file.  Opened in append mode with UTF-8 encoding.
    level : int
        Python logging level for the file handler. Default: ``logging.DEBUG``.
    fmt : str
        Log record format string passed to ``logging.Formatter``.
        Defaults to :data:`DEFAULT_FMT`.
    datefmt : str
        Date format string passed to ``logging.Formatter``.
        Defaults to :data:`DEFAULT_DATEFMT`.
    """

    def __init__(
        self,
        name: str,
        log_file: str,
        level: int = logging.DEBUG,
        fmt: str = DEFAULT_FMT,
        datefmt: str = DEFAULT_DATEFMT,
    ) -> None:
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)

        # Avoid adding duplicate handlers if configure() is called more than once
        if not self._logger.handlers:
            handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
            self._logger.addHandler(handler)

    # ── internal helpers ──────────────────────────────────────────────────────
    def _now(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _print(self, tag: str, msg: str) -> None:
        """Format and flush a single stdout line."""
        prefix = f"[{self._now()}] [{self.name}]"
        suffix = f" [{tag}]" if tag else ""
        print(f"{prefix}{suffix} {msg}", flush=True)

    # ── public logging methods ────────────────────────────────────────────────
    def progress(self, msg: str) -> None:
        """Log an informational message."""
        self._logger.info(msg)
        self._print("", msg)

    def warn(self, msg: str) -> None:
        """Log a warning message."""
        self._logger.warning(msg)
        self._print("WARN", msg)

    def error(self, msg: str) -> None:
        """Log an error message."""
        self._logger.error(msg)
        self._print("ERROR", msg)

    def log_kv(self, prefix: str, **kwargs) -> None:
        """Log a message with optional key=value context pairs.

        Formats as ``"<prefix> | k1=v1, k2=v2, ..."`` when kwargs are given,
        or just ``"<prefix>"`` when called with no extra arguments.
        """
        parts = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self.progress(f"{prefix} | {parts}" if parts else prefix)

    def _heartbeat(self, i: int, total: int, every: int, label: str) -> None:
        """Log periodic progress during a loop."""
        if i % every == 0 or i == total:
            self.progress(f"{label}: {i}/{total}")

    @contextmanager
    def step(self, title: str, **kwargs):
        """Context manager that logs START / END / FAIL with elapsed time.

        On clean exit  → logs ``END <title>`` with elapsed time.
        On exception   → logs ``FAIL <title>`` with elapsed time and the last
                         traceback line, then writes the full traceback to the
                         log file via ``logging.exception``.
                         ``END`` is NOT emitted on failure.

        Usage::

            with pl.step("Load ZIPs", zip_root=path, count=5):
                ...
        """
        _parts = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        _ctx = f" | {_parts}" if _parts else ""

        t0 = time.perf_counter()
        self.progress(f"START {title}{_ctx}")
        _failed = False
        try:
            yield
        except Exception:
            _failed = True
            dt = time.perf_counter() - t0
            _last = traceback.format_exc().strip().splitlines()[-1]
            self.error(f"FAIL {title}: {_last}{_ctx} | elapsed={dt:.2f}s")
            self._logger.exception(f"Step failed: {title}")
            raise
        finally:
            if not _failed:
                dt = time.perf_counter() - t0
                self.progress(f"END {title}{_ctx} | elapsed={dt:.2f}s")


# ── module-level singleton ────────────────────────────────────────────────────
_instance: Optional[Logger] = None


def configure(
    name: str,
    log_file: str,
    level: int = logging.DEBUG,
    fmt: str = DEFAULT_FMT,
    datefmt: str = DEFAULT_DATEFMT,
) -> Logger:
    """Create and register the module-level logger instance.

    Call once from the entry-point script before importing any helper module
    that uses the convenience functions below.

    Returns the created :class:`Logger` instance.
    """
    global _instance
    _instance = Logger(name, log_file, level=level, fmt=fmt, datefmt=datefmt)
    return _instance


def get() -> Logger:
    """Return the configured logger instance.

    :raises RuntimeError: if :func:`configure` has not been called yet.
    """
    if _instance is None:
        raise RuntimeError(
            "Logger is not configured. "
            "Call project_logging.configure(name, log_file) before logging."
        )
    return _instance


# ── module-level convenience functions ───────────────────────────────────────
# Helper modules import these directly so they don't need to carry a logger
# reference through every function signature.

def progress(msg: str) -> None:
    get().progress(msg)


def warn(msg: str) -> None:
    get().warn(msg)


def error(msg: str) -> None:
    get().error(msg)


def log_kv(prefix: str, **kwargs) -> None:
    get().log_kv(prefix, **kwargs)


def step(title: str, **kwargs):
    """Module-level alias for :meth:`Logger.step` (returns the context manager)."""
    return get().step(title, **kwargs)
