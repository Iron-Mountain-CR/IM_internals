# Changelog

All notable changes. to **im-internals** will be documented in this file following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

## [Unreleased]
- (Future enhancements and fixes)

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
[Unreleased]: https://github.com/<company>/im-internals/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/<company>/im-internals/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/<company>/im-internals/compare/v0.2.1...v0.2.2
[0.2.0]: https://github.com/<company>/im-internals/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/<company>/im-internals/releases/tag/v0.1.0
```