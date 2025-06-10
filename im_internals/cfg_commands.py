import argparse
import configparser
import os
import sys


def find_cfg_file(path: str) -> str:
    """
    Locate a .cfg file on disk.

    :param path: Path to a directory or .cfg file.
    :return: Absolute path to the found .cfg file.
    :raises FileNotFoundError: If no .cfg file exists in the directory,
        the file does not exist, or the path is not a .cfg file.

    Example:
        >>> find_cfg_file('/etc/myapp')
        '/etc/myapp/config.cfg'
    """
    path = os.path.abspath(path)
    if os.path.isdir(path):
        for entry in os.listdir(path):
            if entry.lower().endswith('.cfg'):
                return os.path.join(path, entry)
        raise FileNotFoundError(f"No .cfg file found in directory: {path}")
    if path.lower().endswith('.cfg'):
        if os.path.exists(path):
            return path
        raise FileNotFoundError(f"Config file not found: {path}")
    raise FileNotFoundError(f"Path is not a .cfg file: {path}")


def read_cfg_file(config_path: str, client_name: str) -> dict:
    """
    Read and parse a specific client section from a .cfg file.

    :param config_path: Directory or file path for the .cfg file.
    :param client_name: Section name within the .cfg to read.
    :return: Dictionary of key/value pairs from the specified section.
    :raises FileNotFoundError: If the .cfg file or directory cannot be located.
    :raises ValueError: If the .cfg file contains no sections.
    :raises KeyError: If the requested client_name section is missing.

    Example:
        >>> read_cfg_file('/configs', 'AXA')
        {'user': 'axa_user', 'password': 'secret'}
    """
    cfg_file = find_cfg_file(config_path)
    parser = configparser.ConfigParser()
    parser.read(cfg_file)
    if not parser.sections():
        raise ValueError(f"No sections found in config file: {cfg_file}")
    if client_name not in parser.sections():
        raise KeyError(f"Client '{client_name}' not found. Available: {parser.sections()}")
    return dict(parser[client_name])


def list_sections(config_path: str) -> list:
    """
    List all section names in a .cfg file.

    :param config_path: Directory or file path for the .cfg file.
    :return: List of configuration section names.
    :raises FileNotFoundError: If the .cfg file or directory cannot be located.

    Example:
        >>> list_sections('settings.cfg')
        ['DEFAULT', 'AXA', 'XYZ']
    """
    cfg_file = find_cfg_file(config_path)
    parser = configparser.ConfigParser()
    parser.read(cfg_file)
    return parser.sections()


def parse_cli_args(args=None) -> dict:
    """
    Parse command-line arguments for both subcommands and legacy flags.

    Supports:
      - list: --path/-p
      - get:  --path/-p, --client/-c
      - legacy: top-level -p/--path and -c/--client without subcommand.

    :param args: List of arguments (defaults to sys.argv[1:]).
    :return: Dictionary with keys 'command', 'path', and 'client'.
    :raises SystemExit: On argument parsing errors.

    Example:
        >>> parse_cli_args(['list', '-p', '/configs'])
        {'command': 'list', 'path': '/configs', 'client': None}

        >>> parse_cli_args(['-c', 'AXA', '-p', 'cfgs'])
        {'command': 'get', 'path': 'cfgs', 'client': 'AXA'}
    """
    parser = argparse.ArgumentParser(prog='cfg_commands', description='Manage .cfg configuration files')
    subparsers = parser.add_subparsers(dest='command', help="Specify the method! For LEGACY, None/empty works as well")

    # list subcommand
    list_p = subparsers.add_parser('list', help='List all available configuration sections')
    list_p.add_argument('-p', '--path', default='.', help='Path to .cfg file or directory')

    # get subcommand
    get_p = subparsers.add_parser('get', help='Get configuration values for a client')
    get_p.add_argument('-p', '--path', default='.', help='Path to .cfg file or directory')
    get_p.add_argument('-c', '--client', required=True, help='Client section name')

    # legacy compatibility: allow direct -p/-c without subcommand
    parser.add_argument('-p', '--path', help=argparse.SUPPRESS)
    parser.add_argument('-c', '--client', help=argparse.SUPPRESS)

    parsed = parser.parse_args(args or sys.argv[1:])

    # Detect legacy invocation
    if parsed.command is None and getattr(parsed, 'client', None):
        parsed.command = 'get'
    return vars(parsed)


def main():
    """
    This module provides programmatic functions and an argparse-based CLI for managing .cfg files.

    Usage in Python scripts:
        from cfg_commands import read_cfg_file, list_sections

        # Read a specific client section
        cfg = read_cfg_file('/path/to/configs', 'ClientName')

        # List all available sections in the config
        sections = list_sections('/path/to/configs')

    CLI integration (argparse):
        # List all clients
        python cfg_commands.py list -p /path/to/configs

        # Get settings for a specific client
        python cfg_commands.py get -c ClientName -p /path/to/configs

    Legacy single-script calls:
        # Scripts consuming only -p/-c flags can do:
        python your_script.py -p /path/to/configs -c ClientName

        # Then inside your_script.py:
        from cfg_commands import parse_cli_args
        params = parse_cli_args()
        path = params['path']
        client = params['client']

    :return: None
    :raises SystemExit: Exits with code 1 on execution errors.
    """
    params = parse_cli_args()
    cmd = params.pop('command')

    try:
        if cmd == 'list':
            sections = list_sections(params['path'])
            print('Available configurations:')
            for sec in sections:
                print(f'- {sec}')
        elif cmd == 'get':
            data = read_cfg_file(params['path'], params['client'])
            for key, val in data.items():
                print(f"{key}={val}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
