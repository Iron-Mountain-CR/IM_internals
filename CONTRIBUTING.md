# Writing CONTRIBUTING.md to disk for download
content = """# Contributing to im-internals

Thank you for considering contributing to **im-internals**, our internal helper toolkit. To keep the project consistent and maintainable, please follow these guidelines in your contributions.


## Table of Contents
1. [Code Style](#code-style)
2. [Documentation](#documentation)
3. [Assertions](#assertions)
4. [Error Handling & Retries](#error-handling--retries)
5. [Testing](#testing)
6. [Commits & Pull Requests](#commits--pull-requests)
7. [Dependencies & Compatibility](#dependencies--compatibility)

---


## Code Style

- **Python Version**: Target Python 3.10+.
- **Formatting**: Use [Black](https://github.com/psf/black) with default settings. Run `black .` before committing.
- **Linting**: Follow [flake8](https://github.com/PyCQA/flake8) rules. Run `flake8 .` to catch common issues.
- **Type Hints**: Annotate all functions and public methods with type hints. Use `typing` constructs where appropriate.
- **Naming**: Use `snake_case` for functions and variables, `PascalCase` for classes, and `UPPER_CASE` for constants.


## Documentation

- **Docstrings**: Every public function, class, and module must include a docstring following the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
- **README Updates**: If adding new features, update `README.md` to include usage examples and reference new functionality.
- **CHANGELOG**: Maintain `CHANGELOG.md` entries for notable changes, fixes, and improvements.
- **In-line Comments**: Add comments for non-obvious code sections to explain the intent and rationale.


## Assertions

- Use `assert` statements to enforce internal invariants and catch programmer errors early.
- Avoid using `assert` for validating external inputs; instead, raise appropriate exceptions (e.g., `ValueError`, `TypeError`).


## Error Handling & Retries

- **Exceptions**: Catch and handle exceptions thoughtfully. Do not swallow broad exceptions.
- **Retries**: For network or I/O operations (e.g., database queries, FTP/SFTP, API calls), use the [Tenacity](https://github.com/jd/tenacity) library:

  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential

  @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
  def fetch_data(...):
      ...
  ```
  
- **Configurable Parameters**: Allow retry parameters (attempts, wait time) to be configurable via function arguments or environment variables.


## Testing

- **Unit Tests**: Write unit tests using [pytest](https://pytest.org). Place tests in the `tests/` directory mirroring the package structure.  
- **Test Coverage**: Aim for at least 80% coverage. Use `pytest --cov` to measure coverage.  
- **Fixtures & Mocks**: Use `pytest` fixtures and `unittest.mock` for isolating external dependencies (e.g., network, file system).  
- **CI Integration**: Ensure all tests pass locally and in the CI pipeline before submitting a PR.  



## Commits & Pull Requests

- **Branching**: Create feature branches named `feature/<name>` or bugfix branches named `bugfix/<issue-number>-<short-desc>`.  
- **Commit Messages**: Use [Conventional Commits](https://www.conventionalcommits.org/) format:
  ```text
  feat: add SFTP upload helper
  fix: handle timeout in API client
  docs: update README with new CLI options
  ```
- **Signed-off-by**: At the end of each commit message, include a Signed-off-by: trailer with your name and email, for example:
  ```text
  Signed-off-by: Ivan Bilej <ivan.bilej@ironmountain.com>
  ```
  To add this automatically, use:
  ```markdown
  git commit -s -m "<type>: <scope> - <description>"
  ```
  To enable auto sign-off for commits in just this repository, run:
  ```markdown
  git config format.signoff true
  ```
  To enable auto sign-off for all your commits globally, run:
  ```markdown
  git config --global format.signoff true
  ```
- **Pull Request**:
  1. Reference the issue number in the PR title or description.  
  2. Describe the change, motivation, and any relevant details.  
  3. Ensure all checks (lint, tests, type checks) pass.  


## Dependencies & Compatibility

- **Pinning**: For library dependencies, specify minimum versions only. Colleagues may tighten in downstream projects.  
- **Compatibility**: Ensure new code does not break existing functionality. Run the full test suite after updating dependencies.  

