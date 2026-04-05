"""Shared pytest fixtures for dAIly test suite."""
import os

import pytest


@pytest.fixture
def vault_key() -> bytes:
    """Returns a fresh 32-byte key for AES-256 encryption tests."""
    return os.urandom(32)
