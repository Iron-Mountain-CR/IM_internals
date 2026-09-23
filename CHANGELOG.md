# Changelog

All notable changes. to **im-internals** will be documented in this file following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

## [Unreleased]
- (Future enhancements and fixes)

## [0.4.2] - 2026-09-23
### Changed
- Published to PyPI as `im-internals` via Trusted Publishing (OIDC) — `pip install --upgrade
  im-internals` now works directly, no more tracking GitHub release tags/wheel URLs. The source repo
  itself stays private; only the built package is public. The `publish.yaml` workflow previously
  built the package and installed `twine` but never actually called `twine upload` (dead
  `TWINE_USERNAME`/`TWINE_PASSWORD` env vars on an unrelated step) — replaced with a working publish
  step, no API token stored in the repo.

## [0.4.1] - 2026-09-23
### Fixed
- `api.timeout_decorator` no longer runs the wrapped call inside a `ThreadPoolExecutor`. A call that
  genuinely never returned (e.g. a stalled socket) left its worker thread running forever, and
  exiting the `with` block (`exec.shutdown(wait=True)`) — or `concurrent.futures`' own process-wide
  `atexit` hook, which joins *every* worker thread any `ThreadPoolExecutor` in the process ever
  created — blocked interpreter shutdown waiting for it regardless of the configured timeout.
  Replaced with a plain `daemon=True` thread + `Thread.join(timeout)`: a stuck call now reliably
  raises `TimeoutException` after the configured timeout, and the abandoned thread can no longer
  block the process from exiting. Behavior otherwise unchanged (same sequential execution from the
  caller's side, same return values, same exception propagation).

## [0.4.0] - 2026-09-17
### Added
- `Sftp` gains optional `connect_timeout` (default 30s, bounds the SSH handshake) and
  `keepalive_interval` (default 30s, SSH-level keepalive on the transport) constructor parameters.
- `Ftp` gains optional `connect_timeout` (default 60s — also bounds `ftplib`'s data-transfer sockets,
  not just the handshake) and OS-level TCP keepalive on the control socket via a new
  `_enable_tcp_keepalive()` helper.
- Both are optional kwargs with defaults, so existing call sites are unaffected. Without them, a
  connection that went silently dead (VPN blip, firewall idle timeout) had no way to be noticed — the
  socket never errors on its own, so the next read/write, or even `close_connections()`/`__del__` at
  script end, could block forever.

### Fixed
- `Sftp.__del__`/`Ftp.__del__` no longer raise noisy/misleading secondary exceptions when called on a
  partially-constructed instance (an `assert` failed in `__init__` before any attributes were set) or
  during interpreter shutdown (module globals already torn down, e.g. `pl.progress` needing
  `datetime`). Both cases are now swallowed, since Python already discards `__del__` exceptions and
  only prints them as noise.

## [0.3.4] - 2026-09-10
### Fixed
- `transfer.Move.copy_files_or_folders`, `transfer.Move.copy_list_of_files_or_folders`, and
  `transfer.recursive_folder_lookup` called the pre-rewrite two-argument `File(folder, filename)`
  constructor and read a `.md_hash` attribute, both removed when `file.File` was rewritten to its
  current single-argument `File(file_path)` / `.md5` API. Any of the three now raised
  `TypeError: File.__init__() takes 2 positional arguments but 3 were given` as soon as a caller hit
  the file-already-exists/hash-comparison branch (e.g. `Move.copy_files_or_folders(move_folder=True)`
  recursing into an existing destination folder). No test coverage previously touched this path.

## [0.3.0] - 2026-04-02
### Added
- `project_logging` module — centralised logging singleton with `progress`, `warn`,
  `error`, `log_kv`, and `step` helpers, plus stdout formatting with timestamps.

### Changed
- All modules (`api`, `email`, `file`, `folder`, `ftp`, `sanitize`, `sftp`, `sql`,
  `transfer`) migrated from bare `logging.*` / per-instance loggers to the
  `project_logging` singleton.
- `Ftp._log_setup()` and `Sftp._log_setup()` now delegate to `project_logging.get()`
  instead of creating their own `FileHandler`; `logger_name` parameters kept for
  backward compatibility.

## [0.2.2] - 2025-08-14
- Changed name of the package from "im-internals" -> "im_internals"


## [0.2.1] - 2025-06-11
### Added
- Tests from `API` up to `SANITIZE`. Still needs tests for `SFTP, SQL, TRANSFER`
- [publish.yaml](.github%2Fworkflows%2Fpublish.yaml) to build package with every update. Buils upon using `tag vX.X.X` system. Tag should contain the same version as [pyproject.toml](pyproject.toml).

### Changed
- Bumped project version to 0.2.1.
- Added to [CONTRIBUTING.md](CONTRIBUTING.md) the `GIT commands` to verify if user has `Signed-off-by:` added to every commit 


## [0.2.0] - 2025-06-08
### Added
- PDF processing and text extraction utilities via `pypdf`.

### Changed
- Bumped project version to 0.2.0.
- Updated console script entry-point to PEP 621 format under `[project.entry-points]`.
- Cleaned up setuptools-specific package configuration.

## [0.1.0] - 2025-06-01
### Added
- Initial release of internal helper toolkit:
  - Database helpers (`pyodbc`)
  - SFTP & FTP utilities (`paramiko`, `ftplib`)
  - API client wrappers with retry logic (`requests`, `tenacity`)
  - Email send/receive utilities
  - Configurable console script `cfg-commands`

```markdown
[Unreleased]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.3.4...v0.4.0
[0.3.4]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.3.0...v0.3.4
[0.3.0]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Iron-Mountain-CR/IM_internals/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Iron-Mountain-CR/IM_internals/releases/tag/v0.1.0
```