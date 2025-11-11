"""Integration tests for ZRM end-to-end workflows."""

from __future__ import annotations

import threading
import time

import pytest

import zrm
from zrm.generated_protos import example_services_pb2, geometry_pb2


def test_multi_node_pub_sub():
    """Test publisher and subscriber on different nodes."""
    node_pub = zrm.Node("publisher_node")
    node_sub = zrm.Node("subscriber_node")

    received = []

    def callback(msg):
        received.append(msg)

    sub = node_sub.create_subscriber("robot/pose", geometry_pb2.Pose, callback=callback)
    time.sleep(0.2)

    pub = node_pub.create_publisher("robot/pose", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(
        position=geometry_pb2.Point(x=10.0, y=20.0, z=30.0),
        orientation=geometry_pb2.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    )

    pub.publish(msg)
    time.sleep(0.2)

    assert len(received) == 1
    assert received[0].position.x == 10.0
    assert received[0].position.y == 20.0

    pub.close()
    sub.close()
    node_pub.close()
    node_sub.close()


def test_multi_node_service():
    """Test service server and client on different nodes."""
    node_server = zrm.Node("server_node")
    node_client = zrm.Node("client_node")

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = node_server.create_service(
        "compute", example_services_pb2.AddTwoInts, handler
    )
    time.sleep(0.2)

    client = node_client.create_client("compute", example_services_pb2.AddTwoInts)

    request = example_services_pb2.AddTwoInts.Request(a=100, b=200)
    response = client.call(request, timeout=2.0)

    assert response.sum == 300

    client.close()
    server.close()
    node_server.close()
    node_client.close()


def test_multiple_subscribers_same_topic():
    """Test multiple subscribers receiving the same messages."""
    node = zrm.Node("test_node")

    received1 = []
    received2 = []
    received3 = []

    def callback1(msg):
        received1.append(msg)

    def callback2(msg):
        received2.append(msg)

    def callback3(msg):
        received3.append(msg)

    sub1 = node.create_subscriber("topic", geometry_pb2.Pose, callback=callback1)
    sub2 = node.create_subscriber("topic", geometry_pb2.Pose, callback=callback2)
    sub3 = node.create_subscriber("topic", geometry_pb2.Pose, callback=callback3)
    time.sleep(0.2)

    pub = node.create_publisher("topic", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0))
    pub.publish(msg)
    time.sleep(0.2)

    # All subscribers should receive the message
    assert len(received1) == 1
    assert len(received2) == 1
    assert len(received3) == 1

    pub.close()
    sub1.close()
    sub2.close()
    sub3.close()
    node.close()


def test_concurrent_service_calls():
    """Test multiple concurrent service calls."""
    node = zrm.Node("test_node")

    call_count = 0

    def handler(req):
        nonlocal call_count
        call_count += 1
        time.sleep(0.1)  # Simulate work
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = node.create_service("compute", example_services_pb2.AddTwoInts, handler)
    time.sleep(0.2)

    client = node.create_client("compute", example_services_pb2.AddTwoInts)

    results = []
    errors = []

    def make_call(a, b):
        try:
            request = example_services_pb2.AddTwoInts.Request(a=a, b=b)
            response = client.call(request, timeout=5.0)
            results.append(response.sum)
        except Exception as e:
            errors.append(e)

    # Make concurrent calls
    threads = [threading.Thread(target=make_call, args=(i, i * 2)) for i in range(5)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All calls should succeed
    assert len(errors) == 0
    assert len(results) == 5
    assert call_count == 5

    # Verify results
    expected = [0, 3, 6, 9, 12]  # i + i*2 for i in range(5)
    assert sorted(results) == expected

    client.close()
    server.close()
    node.close()


def test_stress_test_pub_sub():
    """Stress test with many messages."""
    node = zrm.Node("test_node")

    received_count = 0
    lock = threading.Lock()

    def callback(msg):
        nonlocal received_count
        with lock:
            received_count += 1

    sub = node.create_subscriber("stress/test", geometry_pb2.Point, callback=callback)
    time.sleep(0.2)

    pub = node.create_publisher("stress/test", geometry_pb2.Point)

    # Send many messages
    num_messages = 100
    for i in range(num_messages):
        msg = geometry_pb2.Point(x=float(i), y=0.0, z=0.0)
        pub.publish(msg)

    time.sleep(1.0)  # Wait for all messages to arrive

    # Should receive all or most messages (allow some loss)
    assert received_count >= num_messages * 0.95  # 95% success rate

    pub.close()
    sub.close()
    node.close()


def test_graph_discovery_across_nodes():
    """Test graph discovery across multiple nodes."""
    node1 = zrm.Node("node1")
    node2 = zrm.Node("node2")
    node3 = zrm.Node("node3")
    time.sleep(0.5)

    # Create various entities
    pub1 = node1.create_publisher("topic1", geometry_pb2.Pose)
    sub2 = node2.create_subscriber("topic1", geometry_pb2.Pose)

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server3 = node3.create_service("service1", example_services_pb2.AddTwoInts, handler)
    time.sleep(0.5)

    # All nodes should see all entities through their graphs
    assert node1.graph.count(zrm.EntityKind.PUBLISHER, "topic1") >= 1
    assert node2.graph.count(zrm.EntityKind.SUBSCRIBER, "topic1") >= 1
    assert node3.graph.count(zrm.EntityKind.SERVICE, "service1") >= 1

    # All nodes should see all other nodes
    node_names = node1.graph.get_node_names()
    assert "node1" in node_names
    assert "node2" in node_names
    assert "node3" in node_names

    pub1.close()
    sub2.close()
    server3.close()
    node1.close()
    node2.close()
    node3.close()


def test_init_shutdown_workflow():
    """Test init/shutdown workflow with multiple nodes."""
    # Initialize ZRM
    zrm.init()

    # Create nodes (should use global context)
    node1 = zrm.Node("node1")
    node2 = zrm.Node("node2")

    pub = node1.create_publisher("topic", geometry_pb2.Pose)
    sub = node2.create_subscriber("topic", geometry_pb2.Pose)

    msg = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0))
    pub.publish(msg)
    time.sleep(0.2)

    received = sub.latest()
    assert received is not None
    assert received.position.x == 1.0

    pub.close()
    sub.close()
    node1.close()
    node2.close()

    # Shutdown
    zrm.shutdown()


def test_complex_workflow_with_chained_services():
    """Test complex workflow with chained service calls."""
    node = zrm.Node("test_node")

    # Service that adds two numbers
    def add_handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = node.create_service("add", example_services_pb2.AddTwoInts, add_handler)
    time.sleep(0.2)

    client = node.create_client("add", example_services_pb2.AddTwoInts)

    # Make chained calls
    result1 = client.call(
        example_services_pb2.AddTwoInts.Request(a=1, b=2), timeout=2.0
    )
    result2 = client.call(
        example_services_pb2.AddTwoInts.Request(a=result1.sum, b=3), timeout=2.0
    )
    result3 = client.call(
        example_services_pb2.AddTwoInts.Request(a=result2.sum, b=4), timeout=2.0
    )

    # 1 + 2 = 3, 3 + 3 = 6, 6 + 4 = 10
    assert result3.sum == 10

    client.close()
    server.close()
    node.close()


def test_pub_sub_different_message_types():
    """Test multiple pub/sub pairs with different message types."""
    node = zrm.Node("test_node")

    received_pose = []
    received_point = []
    received_vector = []

    def callback_pose(msg):
        received_pose.append(msg)

    def callback_point(msg):
        received_point.append(msg)

    def callback_vector(msg):
        received_vector.append(msg)

    sub1 = node.create_subscriber(
        "topic/pose", geometry_pb2.Pose, callback=callback_pose
    )
    sub2 = node.create_subscriber(
        "topic/point", geometry_pb2.Point, callback=callback_point
    )
    sub3 = node.create_subscriber(
        "topic/vector", geometry_pb2.Vector3, callback=callback_vector
    )
    time.sleep(0.2)

    pub1 = node.create_publisher("topic/pose", geometry_pb2.Pose)
    pub2 = node.create_publisher("topic/point", geometry_pb2.Point)
    pub3 = node.create_publisher("topic/vector", geometry_pb2.Vector3)

    msg1 = geometry_pb2.Pose(position=geometry_pb2.Point(x=1.0, y=2.0, z=3.0))
    msg2 = geometry_pb2.Point(x=4.0, y=5.0, z=6.0)
    msg3 = geometry_pb2.Vector3(x=7.0, y=8.0, z=9.0)

    pub1.publish(msg1)
    pub2.publish(msg2)
    pub3.publish(msg3)
    time.sleep(0.2)

    # Each subscriber should receive its message
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
    node.close()
