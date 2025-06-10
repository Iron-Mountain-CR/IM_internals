import pytest
from im_internals.sftp import Sftp

def test_init_invalid_host():
    with pytest.raises(AssertionError):
        Sftp("not.an.ip", "u", "p", ".", ".", ".", "logs", "log.log")

# For full integration tests you’d need a real or mocked Paramiko transport.
