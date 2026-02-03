"""Pytest configuration and shared fixtures for ZRM tests."""

from __future__ import annotations

import pytest

import zrm


@pytest.fixture
def session():
    """Create a fresh ZRM session for testing."""
    sess = zrm.open(name="test_session")
    yield sess
    sess.close()
