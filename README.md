# Writing README.md to disk for download
readme_content = """# im-internals

**im-internals** is an internal helper toolkit developed to streamline common tasks across database operations, (S)FTP transfers, API integrations, email handling, and other utilities within our organization.

## Features

- **Database Helpers**: Simplify connections and queries using `pyodbc`.
- **SFTP & FTP Utilities**: Secure file transfers via `paramiko` and built-in `ftplib` wrappers.
- **API Clients**: Lightweight wrappers for RESTful API interactions using `requests` and retry logic via `tenacity`.
- **Email Utilities**: Send and receive emails with built-in MIME support.
- **Configurable Commands**: Console script `cfg-commands` for running configuration-related tasks.
- **PDF Processing**: Basic PDF manipulation and text extraction using `PyPDF2`.


## Installation

This package is **not published to PyPI** — `pip install im-internals` will not work. Install
directly from a tagged GitHub Release wheel instead:

```bash
python -m pip install --upgrade "https://github.com/Iron-Mountain-CR/IM_internals/releases/download/<tag>/im_internals-<version>-py3-none-any.whl"
```

Replace `<tag>`/`<version>` with the release you want, e.g. for `v0.3.4`:

```bash
python -m pip install --upgrade "https://github.com/Iron-Mountain-CR/IM_internals/releases/download/v0.3.4/im_internals-0.3.4-py3-none-any.whl"
```

Verify the installed version:

```bash
python -c "import im_internals; print(im_internals.__version__)"
```

Alternatively, to always track the latest `main` (rebuilds from source on every install, no URL to
update per release):

```bash
python -m pip install --upgrade "git+https://github.com/Iron-Mountain-CR/IM_internals.git@main"
```


## Quick Start
### Database Example

```python
from im_internals.db import Database

# Initialize and query
db = Database(dsn="MY_DB_DSN")
rows = db.query("SELECT * FROM my_table WHERE status=?", params=("active",))
```


### SFTP Upload

```python
from im_internals.sftp import SFTPClient

client = SFTPClient(host="sftp.example.com", user="user", key_path="~/.ssh/id_rsa")
client.upload_file(local_path="data.csv", remote_path="/incoming/data.csv")
```


### API Request with Retries
```python
from im_internals.api import ApiClient

api = ApiClient(base_url="https://api.example.com", retry_config={"tries":3, "wait":2})
response = api.get("/v1/resource")
```


### Send Email
```python
from im_internals.email import EmailClient

email = EmailClient(smtp_host="smtp.example.com", port=587)
email.send(
    sender="noreply@company.com",
    recipients=["user@company.com"],
    subject="Test Email",
    body="Hello from im-internals!"
)
```


## CLI Usage
```markdown
# View available cfg-commands
cfg-commands --help
```


## Configuration
All configuration parameters—including database DSNs, SFTP credentials, API settings, and email credentials—are managed via company-standard .cfg files stored and secured externally. Do not include any credentials or config files in this repository. 
A typical .cfg file follows the INI format. Example section for email:
```markdown
[email]
host = smtp.example.com
port = 587
user = your_email_username
password = your_email_password
use_tls = true
```
By default, if you omit the -p/--path flag, cfg-commands will scan the current working directory for the first .cfg or .CFG file and use that. There is no built-in default path such as ~/.im-internals.cfg—to specify a file in another location, always use -p <path>.
Clients will inject values into environment variables or client constructors based on the loaded .cfg file.



## Contributing
Thank you for considering contributing to **im-internals**! Please follow the guidelines outlined in [CONTRIBUTING.md](CONTRIBUTING.md) to keep the project consistent and maintainable.


## License
This toolkit is proprietary and intended for internal use only. See the [LICENSE](LICENSE) file at the project root for full terms.
