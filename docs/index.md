# IM Internals

Welcome to the **IM Internals** documentation!  
Here you’ll find everything you need to install, configure, and dive into the internals of the `im_internals` package.

---

## Installation

Published on PyPI as of v0.4.2 (2026-09-23) - the plain command below always installs the latest
release, no GitHub URL or release tag needed:

```bash
pip install --upgrade im-internals
```

Or, if you're working with the source (repo is private - requires access):

```bash
git clone https://github.com/Iron-Mountain-CR/IM_internals.git
cd IM_internals
pip install -e .
```

See [CHANGELOG.md](https://github.com/Iron-Mountain-CR/IM_internals/blob/main/CHANGELOG.md) for
what changed in each release.

---

## Quick Start

```python
from im_internals.folder import Folder
from im_internals.email import SendMail

# Work with folders
folder = Folder("/path/to/data")
folder.sanitize()

# Send a notification
mailer = SendMail(
    mail_receiver="you@example.com",
    mail_subject="Test",
    mail_sender="me@example.com",
    mail_password="secret"
)
mailer.send("Hello from IM Internals!")
```

---

## Documentation

- **API Reference**  
  - [Folder module](api/folder.md)  
  - [File module](api/file.md)  
  - [SFTP module](api/sftp.md)  
  - …and so on (see **API Reference** in the nav)

- **Testing**  
  See the tests in the `/tests` directory for usage examples and edge-case coverage.

---

## Contributing

Feel free to open issues or send pull requests. Please follow the existing docstring conventions (Sphinx/reST style) so mkdocstrings can keep everything up to date automatically.

---

*Generated with [MkDocs](https://www.mkdocs.org/) + [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) + [mkdocstrings](https://mkdocstrings.github.io/).*  
