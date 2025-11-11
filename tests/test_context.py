"""Tests for Context class and global context management."""

from __future__ import annotations

import threading

import pytest
import zenoh

import zrm


def test_context_creation():
    """Test creating a context with default configuration."""
    ctx = zrm.Context()
    assert ctx.session is not None
    assert isinstance(ctx.session, zenoh.Session)
    assert ctx.domain_id == zrm.DOMAIN_ID
    ctx.close()


def test_context_with_custom_domain():
    """Test creating a context with custom domain ID."""
    ctx = zrm.Context(domain_id=42)
    assert ctx.domain_id == 42
    ctx.close()


def test_context_with_custom_config():
    """Test creating a context with custom Zenoh configuration."""
    config = zenoh.Config()
    ctx = zrm.Context(config=config)
    assert ctx.session is not None
    ctx.close()


def test_init_and_shutdown():
    """Test init() and shutdown() functions."""
    # Initialize
    zrm.init()
    assert zrm._global_context is not None

    # Initialize again - should be idempotent (no error)
    zrm.init()
    assert zrm._global_context is not None

    # Shutdown
    zrm.shutdown()
    assert zrm._global_context is None
