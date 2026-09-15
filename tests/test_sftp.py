"""
Tests for im_internals.sftp.Sftp.

Thin stub: only covers the constructor's hostname-format assertion. Does not test any real
SFTP operation (connect/upload/download/list) - those would need a real or mocked Paramiko
transport, per the comment at the bottom of this file.
"""
import pytest
from im_internals.sftp import Sftp

def test_init_invalid_host():
    with pytest.raises(AssertionError):
        Sftp("not.an.ip", "u", "p", ".", ".", ".", "logs", "log.log")

# For full integration tests you’d need a real or mocked Paramiko transport.
