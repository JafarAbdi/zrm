"""Tests for Subscriber class."""

from __future__ import annotations

import threading
import time


import zrm
from zrm.generated_protos import geometry_pb2


def test_subscriber_creation(context):
    """Test creating a subscriber."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )
    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)

    assert sub._topic == "test/topic"
    assert sub._msg_type == geometry_pb2.Pose

    sub.close()


def test_subscriber_latest_no_messages(context):
    """Test latest() returns None when no messages received."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )
    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)

    latest = sub.latest()
    assert latest is None

    sub.close()


def test_subscriber_receives_message(context):
    """Test subscriber receives published messages."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    # Create subscriber first
    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.2)  # Wait for subscriber to be ready

    # Create publisher and send message
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    pub.publish(msg)

    time.sleep(0.2)  # Wait for message to arrive

    # Check received message
    latest = sub.latest()
    assert latest is not None
    assert latest.position.x == 1.0
    assert latest.position.y == 2.0
    assert latest.position.z == 3.0

    pub.close()
    sub.close()


def test_subscriber_latest_is_thread_safe(context):
    """Test that latest() is thread-safe."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.2)

    # Publish initial message
    pub.publish(geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=0.0, z=0.0)))
    time.sleep(0.2)

    results = []
    errors = []

    def read_latest():
        try:
            for _ in range(10):
                msg = sub.latest()
                if msg is not None:
                    results.append(msg.position.x)
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    # Start multiple reader threads
    threads = [threading.Thread(target=read_latest) for _ in range(5)]
    for t in threads:
        t.start()

    # Publish messages from main thread
    for i in range(5):
        pub.publish(
            geometry_pb2.Pose(position=geometry_pb2.Point(x=float(i), y=0.0, z=0.0))
        )
        time.sleep(0.05)

    for t in threads:
        t.join()

    # Should not have any errors from concurrent access
    assert len(errors) == 0
    assert len(results) > 0

    pub.close()
    sub.close()


def test_subscriber_with_callback(context):
    """Test subscriber with callback function."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    received_messages = []

    def callback(msg):
        received_messages.append(msg)

    sub = zrm.Subscriber(
        context, node_entity, "test/topic", geometry_pb2.Pose, callback=callback
    )
    time.sleep(0.2)

    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    msg1 = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=0.0, z=0.0))
    msg2 = geometry_pb2.Pose(position=geometry_pb2.Point(x=2.0, y=0.0, z=0.0))

    pub.publish(msg1)
    time.sleep(0.1)
    pub.publish(msg2)
    time.sleep(0.1)

    # Callback should have been called
    assert len(received_messages) == 2
    assert received_messages[0].position.x == 1.0
    assert received_messages[1].position.x == 2.0

    pub.close()
    sub.close()


def test_subscriber_latest_updates(context):
    """Test that latest() returns the most recent message."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.2)

    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)

    # Publish multiple messages
    for i in range(5):
        msg = geometry_pb2.Pose(position=geometry_pb2.Point(x=float(i), y=0.0, z=0.0))
        pub.publish(msg)
        time.sleep(0.05)

    time.sleep(0.2)

    # Latest should be the last message
    latest = sub.latest()
    assert latest is not None
    assert latest.position.x == 4.0

    pub.close()
    sub.close()


def test_subscriber_type_mismatch_error(context):
    """Test that subscriber rejects messages with type mismatch."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    # Subscriber expects Pose
    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.2)

    # Publisher sends Point
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Point)
    msg = geometry_pb2.Point(x=1.0, y=2.0, z=3.0)
    pub.publish(msg)

    time.sleep(0.2)

    # Subscriber should not have received the message (error in callback)
    latest = sub.latest()
    assert latest is None

    pub.close()
    sub.close()


def test_subscriber_liveliness_registration(context):
    """Test that subscriber registers with liveliness."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.5)

    # Check that subscriber appears in graph
    count = graph.count(zrm.EntityKind.SUBSCRIBER, "test/topic")
    assert count >= 1

    sub.close()
    graph.close()
