"""Tests for protobuf serialization/deserialization functions."""

from __future__ import annotations

import pytest
import zenoh

import zrm
from zrm.generated_protos import geometry_pb2


def test_get_type_name_from_instance():
    """Test get_type_name with a message instance."""
    msg = geometry_pb2.Pose()
    type_name = zrm.get_type_name(msg)
    assert type_name == "zrm.Pose"


def test_get_type_name_from_type():
    """Test get_type_name with a message type."""
    type_name = zrm.get_type_name(geometry_pb2.Pose)
    assert type_name == "zrm.Pose"


def test_serialize():
    """Test _serialize function."""
    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    zbytes = zrm.serialize(msg)
    assert isinstance(zbytes, zenoh.ZBytes)

    # Verify we can reconstruct the message
    reconstructed = geometry_pb2.Pose()
    reconstructed.ParseFromString(zbytes.to_bytes())
    assert reconstructed.position.x == 1.0
    assert reconstructed.position.y == 2.0
    assert reconstructed.position.z == 3.0


def test_deserialize_success():
    """Test _deserialize with matching types."""
    original = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    zbytes = zenoh.ZBytes(original.SerializeToString())
    actual_type_name = "zrm.Pose"

    deserialized = zrm.deserialize(zbytes, geometry_pb2.Pose, actual_type_name)

    assert isinstance(deserialized, geometry_pb2.Pose)
    assert deserialized.position.x == 1.0
    assert deserialized.position.y == 2.0
    assert deserialized.position.z == 3.0


def test_deserialize_type_mismatch():
    """Test _deserialize raises error on type mismatch."""
    msg = geometry_pb2.Pose()
    zbytes = zenoh.ZBytes(msg.SerializeToString())

    # Try to deserialize with wrong type name
    with pytest.raises(
        zrm.MessageTypeMismatchError,
        match="Message type mismatch: expected 'zrm.Pose', got 'zrm.Point'",
    ):
        zrm.deserialize(zbytes, geometry_pb2.Pose, "zrm.Point")


def test_serialize_deserialize_roundtrip():
    """Test full serialization/deserialization roundtrip."""
    original = geometry_pb2.Vector3(x=10.5, y=20.3, z=30.1)

    # Serialize
    zbytes = zrm.serialize(original)
    type_name = zrm.get_type_name(original)

    # Deserialize
    deserialized = zrm.deserialize(zbytes, geometry_pb2.Vector3, type_name)

    # Verify
    assert deserialized.x == original.x
    assert deserialized.y == original.y
    assert deserialized.z == original.z


def test_serialize_empty_message():
    """Test serialization of empty message."""
    msg = geometry_pb2.Pose()
    zbytes = zrm.serialize(msg)
    assert isinstance(zbytes, zenoh.ZBytes)

    # Deserialize and verify
    deserialized = zrm.deserialize(zbytes, geometry_pb2.Pose, "zrm.Pose")
    assert isinstance(deserialized, geometry_pb2.Pose)


def test_serialize_nested_message():
    """Test serialization of message with nested fields."""
    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    zbytes = zrm.serialize(msg)
    type_name = zrm.get_type_name(msg)

    deserialized = zrm.deserialize(zbytes, geometry_pb2.Pose, type_name)

    assert deserialized.position.x == 1.0
    assert deserialized.position.y == 2.0
    assert deserialized.position.z == 3.0
    assert deserialized.orientation.w == 1.0
