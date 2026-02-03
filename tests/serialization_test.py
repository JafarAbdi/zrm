"""Tests for protobuf serialization/deserialization functions."""

from __future__ import annotations

import zenoh

import zrm
from zrm.msgs import geometry_pb2


def test_type_name_from_instance():
    """Test _type_name with a message instance."""
    msg = geometry_pb2.Pose()
    type_name = zrm._type_name(msg)
    assert type_name == "zrm/msgs/geometry/Pose"


def test_type_name_from_type():
    """Test _type_name with a message type."""
    type_name = zrm._type_name(geometry_pb2.Pose)
    assert type_name == "zrm/msgs/geometry/Pose"


def test_serialize():
    """Test _serialize function."""
    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    zbytes = zrm._serialize(msg)
    assert isinstance(zbytes, zenoh.ZBytes)

    # Verify we can reconstruct the message.
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
    deserialized = zrm._deserialize(zbytes, geometry_pb2.Pose)

    assert isinstance(deserialized, geometry_pb2.Pose)
    assert deserialized.position.x == 1.0
    assert deserialized.position.y == 2.0
    assert deserialized.position.z == 3.0


def test_serialize_deserialize_roundtrip():
    """Test full serialization/deserialization roundtrip."""
    original = geometry_pb2.Vector3(x=10.5, y=20.3, z=30.1)

    zbytes = zrm._serialize(original)
    deserialized = zrm._deserialize(zbytes, geometry_pb2.Vector3)

    assert deserialized.x == original.x
    assert deserialized.y == original.y
    assert deserialized.z == original.z


def test_serialize_empty_message():
    """Test serialization of empty message."""
    msg = geometry_pb2.Pose()
    zbytes = zrm._serialize(msg)
    assert isinstance(zbytes, zenoh.ZBytes)

    deserialized = zrm._deserialize(zbytes, geometry_pb2.Pose)
    assert isinstance(deserialized, geometry_pb2.Pose)


def test_serialize_nested_message():
    """Test serialization of message with nested fields."""
    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    zbytes = zrm._serialize(msg)
    deserialized = zrm._deserialize(zbytes, geometry_pb2.Pose)

    assert deserialized.position.x == 1.0
    assert deserialized.position.y == 2.0
    assert deserialized.position.z == 3.0
    assert deserialized.orientation.w == 1.0
