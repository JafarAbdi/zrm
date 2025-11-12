"""Tests for Node class."""

from __future__ import annotations

import time


import zrm
from zrm.generated_protos import example_services_pb2, geometry_pb2


def test_node_creation(global_context):
    """Test creating a node."""
    node = zrm.Node("test_node")
    assert node.name == "test_node"
    assert node.graph is not None
    node.close()


def test_node_with_custom_context():
    """Test creating a node with custom context."""
    ctx = zrm.Context()
    node = zrm.Node("test_node", context=ctx)

    assert node.name == "test_node"

    node.close()
    ctx.close()


def test_node_create_publisher(global_context):
    """Test creating a publisher from node."""
    node = zrm.Node("test_node")

    pub = node.create_publisher("test/topic", geometry_pb2.Pose)
    assert pub is not None
    assert isinstance(pub, zrm.Publisher)

    pub.close()
    node.close()


def test_node_create_subscriber(global_context):
    """Test creating a subscriber from node."""
    node = zrm.Node("test_node")

    sub = node.create_subscriber("test/topic", geometry_pb2.Pose)
    assert sub is not None
    assert isinstance(sub, zrm.Subscriber)

    sub.close()
    node.close()


def test_node_create_subscriber_with_callback(global_context):
    """Test creating a subscriber with callback from node."""
    node = zrm.Node("test_node")
    received = []

    def callback(msg):
        received.append(msg)

    sub = node.create_subscriber("test/topic", geometry_pb2.Pose, callback=callback)
    assert sub is not None
    assert sub._callback == callback

    sub.close()
    node.close()


def test_node_create_service(global_context):
    """Test creating a service from node."""
    node = zrm.Node("test_node")

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = node.create_service(
        "add_service",
        example_services_pb2.AddTwoInts,
        handler,
    )

    assert server is not None
    assert isinstance(server, zrm.ServiceServer)

    server.close()
    node.close()


def test_node_create_client(global_context):
    """Test creating a service client from node."""
    node = zrm.Node("test_node")

    client = node.create_client("add_service", example_services_pb2.AddTwoInts)

    assert client is not None
    assert isinstance(client, zrm.ServiceClient)

    client.close()
    node.close()


def test_node_full_pub_sub_workflow():
    """Test complete pub/sub workflow through node."""
    node = zrm.Node("test_node")

    sub = node.create_subscriber("test/topic", geometry_pb2.Pose)
    pub = node.create_publisher("test/topic", geometry_pb2.Pose)

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
    node.close()


def test_node_full_service_workflow():
    """Test complete service workflow through node."""
    node = zrm.Node("test_node")

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = node.create_service(
        "add_service", example_services_pb2.AddTwoInts, handler
    )
    time.sleep(0.2)

    client = node.create_client("add_service", example_services_pb2.AddTwoInts)

    request = example_services_pb2.AddTwoInts.Request(a=10, b=20)
    response = client.call(request, timeout=2.0)

    assert response.sum == 30

    client.close()
    server.close()
    node.close()


def test_node_graph_discovery():
    """Test that node's graph can discover entities."""
    node = zrm.Node("test_node")
    pub = node.create_publisher("test/topic", geometry_pb2.Pose)
    time.sleep(0.1)

    # Node's graph should discover the publisher
    count = node.graph.count(zrm.EntityKind.PUBLISHER, "test/topic")
    assert count == 1

    pub.close()
    node.close()


def test_node_registers_in_graph():
    """Test that node itself registers in the graph."""
    node1 = zrm.Node("node1")
    node2 = zrm.Node("node2")
    time.sleep(0.25)

    # Node should be able to discover other nodes
    node_names = node1.graph.get_node_names()
    assert "node1" in node_names
    assert "node2" in node_names

    node1.close()
    node2.close()


def test_node_multiple_publishers():
    """Test creating multiple publishers from same node."""
    node = zrm.Node("test_node")

    pub1 = node.create_publisher("topic1", geometry_pb2.Pose)
    pub2 = node.create_publisher("topic2", geometry_pb2.Point)
    pub3 = node.create_publisher("topic3", geometry_pb2.Vector3)

    # All should be created successfully
    assert pub1 is not None
    assert pub2 is not None
    assert pub3 is not None

    pub1.close()
    pub2.close()
    pub3.close()
    node.close()


def test_node_multiple_subscribers():
    """Test creating multiple subscribers from same node."""
    node = zrm.Node("test_node")

    sub1 = node.create_subscriber("topic1", geometry_pb2.Pose)
    sub2 = node.create_subscriber("topic2", geometry_pb2.Point)
    sub3 = node.create_subscriber("topic3", geometry_pb2.Vector3)

    # All should be created successfully
    assert sub1 is not None
    assert sub2 is not None
    assert sub3 is not None

    sub1.close()
    sub2.close()
    sub3.close()
    node.close()


def test_node_mixed_entities():
    """Test creating mixed entities (pub/sub/service/client) from node."""
    node = zrm.Node("test_node")

    pub = node.create_publisher("topic1", geometry_pb2.Pose)
    sub = node.create_subscriber("topic2", geometry_pb2.Point)

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = node.create_service("service1", example_services_pb2.AddTwoInts, handler)
    client = node.create_client("service2", example_services_pb2.AddTwoInts)

    # All should be created successfully
    assert pub is not None
    assert sub is not None
    assert server is not None
    assert client is not None

    pub.close()
    sub.close()
    server.close()
    client.close()
    node.close()


def test_node_close_cleans_up():
    """Test that closing node cleans up resources."""
    node = zrm.Node("test_node")

    pub = node.create_publisher("test/topic", geometry_pb2.Pose)
    time.sleep(0.25)

    # Should appear in graph
    count_before = node.graph.count(zrm.EntityKind.PUBLISHER, "test/topic")
    assert count_before == 1

    # Close publisher
    pub.close()

    # Poll for cleanup with timeout
    max_wait = 2.0
    interval = 0.1
    elapsed = 0.0
    count_after = count_before

    while elapsed < max_wait and count_after > 0:
        time.sleep(interval)
        elapsed += interval
        count_after = node.graph.count(zrm.EntityKind.PUBLISHER, "test/topic")

    # Should eventually be removed from graph
    assert count_after == 0, (
        f"Expected 0 publishers after close, got {count_after} after {elapsed}s"
    )

    node.close()
