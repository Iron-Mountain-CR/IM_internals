# Changelog

All notable changes. to **im-internals** will be documented in this file following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

## [Unreleased]
- (Future enhancements and fixes)


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
[Unreleased]: https://github.com/<company>/im-internals/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/<company>/im-internals/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/<company>/im-internals/releases/tag/v0.1.0
```