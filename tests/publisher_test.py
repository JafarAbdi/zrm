"""Tests for Publisher class."""

from __future__ import annotations

import time

import pytest

import zrm
from zrm.generated_protos import geometry_pb2


def test_publisher_creation(context, node):
    """Test creating a publisher."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)

    assert pub._topic == "test/topic"
    assert pub._msg_type == geometry_pb2.Pose

    pub.close()


def test_publisher_publish_valid_message(context, node):
    """Test publishing a valid message."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    # Should not raise
    pub.publish(msg)

    pub.close()


def test_publisher_publish_wrong_type(context, node):
    """Test publishing a message of wrong type raises TypeError."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)

    # Try to publish wrong type
    wrong_msg = geometry_pb2.Point(x=1.0, y=2.0, z=3.0)

    with pytest.raises(
        TypeError,
        match="Expected message of type Pose, got Point",
    ):
        pub.publish(wrong_msg)

    pub.close()


def test_publisher_close(context, node):
    """Test closing a publisher."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    pub.close()

    # Verify liveliness token is undeclared (implicit - no exception should be raised)


def test_publisher_liveliness_registration(context, node):
    """Test that publisher registers with liveliness."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)  # Wait for graph to initialize

    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.5)  # Wait for liveliness to propagate

    # Check that publisher appears in graph
    count = graph.count(zrm.EntityKind.PUBLISHER, "test/topic")
    assert count >= 1

    pub.close()
    graph.close()


def test_publisher_multiple_on_same_topic(context):
    """Test multiple publishers on the same topic."""
    node_entity1 = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="node1",
    )
    node_entity2 = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="node2",
    )

    pub1 = zrm.Publisher(context, node_entity1, "test/topic", geometry_pb2.Pose)
    pub2 = zrm.Publisher(context, node_entity2, "test/topic", geometry_pb2.Pose)

    # Both should work independently
    msg1 = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=0.0, z=0.0))
    msg2 = geometry_pb2.Pose(position=geometry_pb2.Point(x=2.0, y=0.0, z=0.0))

    pub1.publish(msg1)
    pub2.publish(msg2)

    pub1.close()
    pub2.close()
