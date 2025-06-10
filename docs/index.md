# IM Internals

Welcome to the **IM Internals** documentation!  
Here you’ll find everything you need to install, configure, and dive into the internals of the `im_internals` package.

---

## Installation

```bash
pip install im-internals
```

Or, if you’re working with the source:

```bash
git clone https://github.com/Ivan-Bilej/IM_internals
cd im-internals
pip install -e .
```

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
