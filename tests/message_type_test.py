"""Tests for message type identifier functions."""

from __future__ import annotations

import pytest

import zrm
from zrm.msgs import geometry_pb2
from zrm.srvs import std_pb2


def test_get_type_name_from_message_instance():
    """Test get_type_name with a message instance."""
    point = geometry_pb2.Point(x=1.0, y=2.0, z=3.0)
    type_name = zrm.get_type_name(point)
    assert type_name == "zrm/msgs/geometry/Point"


def test_get_type_name_from_message_type():
    """Test get_type_name with a message type."""
    type_name = zrm.get_type_name(geometry_pb2.Point)
    assert type_name == "zrm/msgs/geometry/Point"


def test_get_type_name_from_service_type():
    """Test get_type_name with a service type."""
    type_name = zrm.get_type_name(std_pb2.Trigger)
    assert type_name == "zrm/srvs/std/Trigger"


def test_get_type_name_from_nested_service_message():
    """Test get_type_name with nested service Request/Response."""
    request_type_name = zrm.get_type_name(std_pb2.Trigger.Request)
    assert request_type_name == "zrm/srvs/std/Trigger.Request"

    response_type_name = zrm.get_type_name(std_pb2.Trigger.Response)
    assert response_type_name == "zrm/srvs/std/Trigger.Response"


def test_get_message_type_simple_message():
    """Test get_message_type with a simple message."""
    Point = zrm.get_message_type("zrm/msgs/geometry/Point")
    assert Point is geometry_pb2.Point

    # Verify we can create instances
    point = Point(x=1.0, y=2.0, z=3.0)
    assert point.x == 1.0
    assert point.y == 2.0
    assert point.z == 3.0


def test_get_message_type_service():
    """Test get_message_type with a service type."""
    Trigger = zrm.get_message_type("zrm/srvs/std/Trigger")
    assert Trigger is std_pb2.Trigger


def test_get_message_type_nested_service_message():
    """Test get_message_type with nested service messages."""
    TriggerRequest = zrm.get_message_type("zrm/srvs/std/Trigger.Request")
    assert TriggerRequest is std_pb2.Trigger.Request

    TriggerResponse = zrm.get_message_type("zrm/srvs/std/Trigger.Response")
    assert TriggerResponse is std_pb2.Trigger.Response

    # Verify we can create instances
    request = TriggerRequest()
    response = TriggerResponse(success=True, message="Test")
    assert response.success is True
    assert response.message == "Test"


def test_get_message_type_invalid_format():
    """Test get_message_type with invalid identifier format."""
    with pytest.raises(ValueError, match="Invalid identifier format"):
        zrm.get_message_type("invalid")

    with pytest.raises(ValueError, match="Invalid identifier format"):
        zrm.get_message_type("zrm/msgs/geometry")  # Missing type name


def test_get_message_type_invalid_category():
    """Test get_message_type with invalid category."""
    with pytest.raises(ValueError, match="Category must be 'msgs', 'srvs', or 'actions'"):
        zrm.get_message_type("zrm/invalid/geometry/Point")


def test_get_message_type_nonexistent_module():
    """Test get_message_type with nonexistent module."""
    with pytest.raises(ImportError, match="Failed to import module"):
        zrm.get_message_type("zrm/msgs/nonexistent/Point")


def test_get_message_type_nonexistent_type():
    """Test get_message_type with nonexistent type in valid module."""
    with pytest.raises(AttributeError, match="Type .* not found"):
        zrm.get_message_type("zrm/msgs/geometry/NonexistentType")


def test_roundtrip_message():
    """Test roundtrip: type -> identifier -> type for messages."""
    # Start with a type
    original_type = geometry_pb2.Pose2D

    # Get identifier
    identifier = zrm.get_type_name(original_type)
    assert identifier == "zrm/msgs/geometry/Pose2D"

    # Get type back
    retrieved_type = zrm.get_message_type(identifier)
    assert retrieved_type is original_type


def test_roundtrip_service():
    """Test roundtrip: type -> identifier -> type for services."""
    # Start with nested service type
    original_type = std_pb2.Trigger.Request

    # Get identifier
    identifier = zrm.get_type_name(original_type)
    assert identifier == "zrm/srvs/std/Trigger.Request"

    # Get type back
    retrieved_type = zrm.get_message_type(identifier)
    assert retrieved_type is original_type


def test_multiple_message_types():
    """Test get_type_name and get_message_type with various message types."""
    test_cases = [
        (geometry_pb2.Point, "zrm/msgs/geometry/Point"),
        (geometry_pb2.Vector3, "zrm/msgs/geometry/Vector3"),
        (geometry_pb2.Quaternion, "zrm/msgs/geometry/Quaternion"),
        (geometry_pb2.Pose, "zrm/msgs/geometry/Pose"),
        (geometry_pb2.Pose2D, "zrm/msgs/geometry/Pose2D"),
        (geometry_pb2.Twist, "zrm/msgs/geometry/Twist"),
    ]

    for msg_type, expected_identifier in test_cases:
        # Test get_type_name
        identifier = zrm.get_type_name(msg_type)
        assert identifier == expected_identifier, f"Failed for {msg_type}"

        # Test get_message_type
        retrieved_type = zrm.get_message_type(identifier)
        assert retrieved_type is msg_type, f"Failed roundtrip for {msg_type}"
