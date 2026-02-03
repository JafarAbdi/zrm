"""Tests for Publisher and Subscriber."""

from __future__ import annotations

import time

import pytest

import zrm
from zrm.msgs import geometry_pb2


def test_publisher_creation(session):
    """Test creating a publisher."""
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)
    assert pub is not None
    pub.close()


def test_publisher_invalid_topic():
    """Test that publisher rejects topic starting with /."""
    with zrm.open() as session:
        with pytest.raises(ValueError, match="cannot start with '/'"):
            zrm.Publisher(session, "/test/topic", geometry_pb2.Pose)


def test_subscriber_creation(session):
    """Test creating a subscriber."""
    sub = zrm.Subscriber(session, "test/topic", geometry_pb2.Pose)
    assert sub is not None
    sub.close()


def test_subscriber_invalid_topic():
    """Test that subscriber rejects topic starting with /."""
    with zrm.open() as session:
        with pytest.raises(ValueError, match="cannot start with '/'"):
            zrm.Subscriber(session, "/test/topic", geometry_pb2.Pose)


def test_subscriber_with_callback(session):
    """Test creating a subscriber with callback."""
    received = []

    def callback(msg):
        received.append(msg)

    sub = zrm.Subscriber(session, "test/topic", geometry_pb2.Pose, callback=callback)
    assert sub is not None
    sub.close()


def test_pub_sub_workflow(session):
    """Test complete pub/sub workflow."""
    sub = zrm.Subscriber(session, "test/topic", geometry_pb2.Pose)
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    pub.publish(msg)
    time.sleep(0.2)

    received = sub.latest()
    assert received is not None
    assert received.position.x == 1.0
    assert received.position.y == 2.0

    pub.close()
    sub.close()


def test_pub_sub_with_callback(session):
    """Test pub/sub with callback."""
    received = []

    def callback(msg):
        received.append(msg)

    sub = zrm.Subscriber(session, "test/topic", geometry_pb2.Pose, callback=callback)
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(position=geometry_pb2.Point(x=5.0, y=6.0, z=7.0))

    pub.publish(msg)
    time.sleep(0.2)

    assert len(received) == 1
    assert received[0].position.x == 5.0

    pub.close()
    sub.close()


def test_multiple_subscribers_same_topic(session):
    """Test multiple subscribers receiving the same messages."""
    received1 = []
    received2 = []
    received3 = []

    def callback1(msg):
        received1.append(msg)

    def callback2(msg):
        received2.append(msg)

    def callback3(msg):
        received3.append(msg)

    sub1 = zrm.Subscriber(session, "topic", geometry_pb2.Pose, callback=callback1)
    sub2 = zrm.Subscriber(session, "topic", geometry_pb2.Pose, callback=callback2)
    sub3 = zrm.Subscriber(session, "topic", geometry_pb2.Pose, callback=callback3)
    time.sleep(0.2)

    pub = zrm.Publisher(session, "topic", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0))
    pub.publish(msg)
    time.sleep(0.2)

    # All subscribers should receive the message.
    assert len(received1) == 1
    assert len(received2) == 1
    assert len(received3) == 1

    pub.close()
    sub1.close()
    sub2.close()
    sub3.close()


def test_publisher_type_validation(session):
    """Test that publisher validates message type."""
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)

    # Wrong message type should raise.
    with pytest.raises(TypeError, match="Expected Pose, got Point"):
        pub.publish(geometry_pb2.Point(x=1.0, y=2.0, z=3.0))

    pub.close()


def test_pub_sub_different_message_types(session):
    """Test multiple pub/sub pairs with different message types."""
    received_pose = []
    received_point = []
    received_vector = []

    def callback_pose(msg):
        received_pose.append(msg)

    def callback_point(msg):
        received_point.append(msg)

    def callback_vector(msg):
        received_vector.append(msg)

    sub1 = zrm.Subscriber(session, "topic/pose", geometry_pb2.Pose, callback=callback_pose)
    sub2 = zrm.Subscriber(session, "topic/point", geometry_pb2.Point, callback=callback_point)
    sub3 = zrm.Subscriber(session, "topic/vector", geometry_pb2.Vector3, callback=callback_vector)
    time.sleep(0.2)

    pub1 = zrm.Publisher(session, "topic/pose", geometry_pb2.Pose)
    pub2 = zrm.Publisher(session, "topic/point", geometry_pb2.Point)
    pub3 = zrm.Publisher(session, "topic/vector", geometry_pb2.Vector3)

    msg1 = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0))
    msg2 = geometry_pb2.Point(x=4.0, y=5.0, z=6.0)
    msg3 = geometry_pb2.Vector3(x=7.0, y=8.0, z=9.0)

    pub1.publish(msg1)
    pub2.publish(msg2)
    pub3.publish(msg3)
    time.sleep(0.2)

    # Each subscriber should receive its message.
    assert len(received_pose) == 1
    assert len(received_point) == 1
    assert len(received_vector) == 1

    assert received_pose[0].position.x == 1.0
    assert received_point[0].x == 4.0
    assert received_vector[0].x == 7.0

    pub1.close()
    pub2.close()
    pub3.close()
    sub1.close()
    sub2.close()
    sub3.close()
