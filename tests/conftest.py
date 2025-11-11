"""Pytest configuration and shared fixtures for ZRM tests."""

from __future__ import annotations

import time

import pytest

import zrm
from zrm.generated_protos import example_services_pb2, geometry_pb2


@pytest.fixture(autouse=True)
def reset_global_context():
    """Reset global context before and after each test for isolation."""
    # Clean up before test
    if zrm._global_context is not None:
        zrm.shutdown()

    yield

    # Clean up after test
    if zrm._global_context is not None:
        zrm.shutdown()


@pytest.fixture
def global_context():
    """Explicitly initialize global context for tests that need it."""
    zrm.init()
    yield
    zrm.shutdown()


@pytest.fixture
def context():
    """Create a fresh ZRM context for testing (for tests that need explicit context)."""
    ctx = zrm.Context()
    yield ctx
    ctx.close()


@pytest.fixture
def node():
    """Create a test node using global context."""
    test_node = zrm.Node("test_node")
    yield test_node
    test_node.close()
