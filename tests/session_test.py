"""Tests for Session class."""

from __future__ import annotations

import zenoh

import zrm


def test_session_creation():
    """Test creating a session with default configuration."""
    session = zrm.open()
    assert session.zenoh is not None
    assert isinstance(session.zenoh, zenoh.Session)
    assert session.domain == zrm.DOMAIN_DEFAULT
    session.close()


def test_session_with_custom_domain():
    """Test creating a session with custom domain ID."""
    session = zrm.open(domain=42)
    assert session.domain == 42
    session.close()


def test_session_with_custom_config():
    """Test creating a session with custom Zenoh configuration."""
    config = zenoh.Config()
    session = zrm.open(config=config)
    assert session.zenoh is not None
    session.close()


def test_session_context_manager():
    """Test session as context manager."""
    with zrm.open() as session:
        assert session.zenoh is not None
        assert session.domain == zrm.DOMAIN_DEFAULT
        assert session.zid is not None
    # Session should be closed after exiting context


def test_session_zid():
    """Test that session has a Zenoh ID."""
    with zrm.open() as session:
        assert session.zid is not None
        assert isinstance(session.zid, str)
        assert len(session.zid) > 0


def test_session_default_name():
    """Test that session name defaults to the Zenoh ID."""
    with zrm.open() as session:
        assert session.name == session.zid


def test_session_custom_name():
    """Test creating a session with a custom name."""
    with zrm.open(name="my_robot") as session:
        assert session.name == "my_robot"
