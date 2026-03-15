"""Tests for Graph (discovery)."""

from __future__ import annotations

import time

import zrm
from zrm.msgs import geometry_pb2
from zrm.srvs import examples_pb2


def test_graph_creation(session):
    """Test creating a graph."""
    graph = zrm.Graph(session)
    assert graph is not None
    graph.close()


def test_graph_discovers_publisher(session):
    """Test that graph discovers publishers."""
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    publishers = graph.get_publishers("test/topic")
    assert len(publishers) >= 1

    entity = publishers[0]
    assert entity.kind == zrm.EntityKind.PUBLISHER
    assert entity.topic == "test/topic"
    assert "geometry" in entity.type_name
    assert entity.name == "test_session"

    pub.close()
    graph.close()


def test_graph_discovers_subscriber(session):
    """Test that graph discovers subscribers."""
    sub = zrm.Subscriber(session, "test/topic", geometry_pb2.Pose)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    subscribers = graph.get_subscribers("test/topic")
    assert len(subscribers) >= 1

    entity = subscribers[0]
    assert entity.kind == zrm.EntityKind.SUBSCRIBER
    assert entity.topic == "test/topic"

    sub.close()
    graph.close()


def test_graph_discovers_server(session):
    """Test that graph discovers servers."""
    def handler(req):
        return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.Server(session, "add_service", examples_pb2.AddTwoInts, handler)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    servers = graph.get_servers("add_service")
    assert len(servers) >= 1

    entity = servers[0]
    assert entity.kind == zrm.EntityKind.SERVER
    assert entity.topic == "add_service"

    server.close()
    graph.close()


def test_graph_discovers_client(session):
    """Test that graph discovers clients."""
    client = zrm.Client(session, "add_service", examples_pb2.AddTwoInts)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    clients = graph.get_clients("add_service")
    assert len(clients) >= 1

    entity = clients[0]
    assert entity.kind == zrm.EntityKind.CLIENT
    assert entity.topic == "add_service"

    client.close()
    graph.close()


def test_graph_get_topics(session):
    """Test getting all topics."""
    pub1 = zrm.Publisher(session, "topic1", geometry_pb2.Pose)
    pub2 = zrm.Publisher(session, "topic2", geometry_pb2.Point)
    sub = zrm.Subscriber(session, "topic3", geometry_pb2.Vector3)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    topics = graph.get_topics()
    topic_names = [t[0] for t in topics]

    assert "topic1" in topic_names
    assert "topic2" in topic_names
    assert "topic3" in topic_names

    pub1.close()
    pub2.close()
    sub.close()
    graph.close()


def test_graph_get_services(session):
    """Test getting all services."""
    def handler(req):
        return examples_pb2.AddTwoInts.Response(sum=0)

    server = zrm.Server(session, "service1", examples_pb2.AddTwoInts, handler)
    client = zrm.Client(session, "service2", examples_pb2.AddTwoInts)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    services = graph.get_services()
    service_names = [s[0] for s in services]

    assert "service1" in service_names
    assert "service2" in service_names

    server.close()
    client.close()
    graph.close()


def test_graph_wait_for_publisher(session):
    """Test waiting for a publisher."""
    graph = zrm.Graph(session)

    # Publisher doesn't exist yet.
    assert graph.wait_for_publisher("test/topic", timeout=0.1) is False

    # Create publisher in background.
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)

    # Should find it now.
    assert graph.wait_for_publisher("test/topic", timeout=1.0) is True

    pub.close()
    graph.close()


def test_graph_wait_for_subscriber(session):
    """Test waiting for a subscriber."""
    graph = zrm.Graph(session)

    # Subscriber doesn't exist yet.
    assert graph.wait_for_subscriber("test/topic", timeout=0.1) is False

    # Create subscriber.
    sub = zrm.Subscriber(session, "test/topic", geometry_pb2.Pose)

    # Should find it now.
    assert graph.wait_for_subscriber("test/topic", timeout=1.0) is True

    sub.close()
    graph.close()


def test_graph_wait_for_server(session):
    """Test waiting for a server."""
    graph = zrm.Graph(session)

    # Server doesn't exist yet.
    assert graph.wait_for_server("add_service", timeout=0.1) is False

    # Create server.
    def handler(req):
        return examples_pb2.AddTwoInts.Response(sum=0)

    server = zrm.Server(session, "add_service", examples_pb2.AddTwoInts, handler)

    # Should find it now.
    assert graph.wait_for_server("add_service", timeout=1.0) is True

    server.close()
    graph.close()


def test_graph_wait_for_client(session):
    """Test waiting for a client."""
    graph = zrm.Graph(session)

    # Client doesn't exist yet.
    assert graph.wait_for_client("add_service", timeout=0.1) is False

    # Create client.
    client = zrm.Client(session, "add_service", examples_pb2.AddTwoInts)

    # Should find it now.
    assert graph.wait_for_client("add_service", timeout=1.0) is True

    client.close()
    graph.close()


def test_graph_entity_removal(session):
    """Test that graph tracks entity removal."""
    pub = zrm.Publisher(session, "test/topic", geometry_pb2.Pose)
    graph = zrm.Graph(session)
    time.sleep(0.2)

    # Should appear in graph.
    publishers = graph.get_publishers("test/topic")
    assert len(publishers) >= 1

    # Close publisher.
    pub.close()

    # Poll for cleanup with timeout.
    max_wait = 2.0
    interval = 0.1
    elapsed = 0.0

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval
        publishers = graph.get_publishers("test/topic")
        if len(publishers) == 0:
            break

    # Should eventually be removed from graph.
    assert len(publishers) == 0, f"Expected 0 publishers after close, got {len(publishers)}"

    graph.close()
