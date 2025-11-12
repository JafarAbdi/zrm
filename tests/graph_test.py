"""Tests for Graph class and discovery."""

from __future__ import annotations

import time

import pytest

import zrm
from zrm.generated_protos import example_services_pb2, geometry_pb2


def test_graph_creation(context):
    """Test creating a graph."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    assert graph is not None
    graph.close()


def test_graph_discovers_publisher(context):
    """Test that graph discovers publishers."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    # Create publisher
    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.5)

    # Check discovery
    count = graph.count(zrm.EntityKind.PUBLISHER, "test/topic")
    assert count >= 1

    pub.close()
    graph.close()


def test_graph_discovers_subscriber(context):
    """Test that graph discovers subscribers."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    # Create subscriber
    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.5)

    # Check discovery
    count = graph.count(zrm.EntityKind.SUBSCRIBER, "test/topic")
    assert count >= 1

    sub.close()
    graph.close()


def test_graph_discovers_service(context):
    """Test that graph discovers services."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.ServiceServer(
        context,
        node_entity,
        "test_service",
        example_services_pb2.AddTwoInts,
        handler,
    )
    time.sleep(0.5)

    # Check discovery
    count = graph.count(zrm.EntityKind.SERVICE, "test_service")
    assert count >= 1

    server.close()
    graph.close()


def test_graph_discovers_client(context):
    """Test that graph discovers service clients."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    client = zrm.ServiceClient(
        context,
        node_entity,
        "test_service",
        example_services_pb2.AddTwoInts,
    )
    time.sleep(0.5)

    # Check discovery
    count = graph.count(zrm.EntityKind.CLIENT, "test_service")
    assert count >= 1

    client.close()
    graph.close()


def test_graph_count_node_raises_error(context):
    """Test that counting NODE kind raises ValueError."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)

    with pytest.raises(ValueError, match="Use count_by_node"):
        graph.count(zrm.EntityKind.NODE, "test")

    graph.close()


def test_graph_get_entities_by_topic(context):
    """Test getting entities by topic."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    pub = zrm.Publisher(context, node_entity, "test/topic", geometry_pb2.Pose)
    sub = zrm.Subscriber(context, node_entity, "test/topic", geometry_pb2.Pose)
    time.sleep(0.5)

    # Get publishers
    publishers = graph.get_entities_by_topic(zrm.EntityKind.PUBLISHER, "test/topic")
    assert len(publishers) >= 1

    # Get subscribers
    subscribers = graph.get_entities_by_topic(zrm.EntityKind.SUBSCRIBER, "test/topic")
    assert len(subscribers) >= 1

    pub.close()
    sub.close()
    graph.close()


def test_graph_get_entities_by_topic_invalid_kind(context):
    """Test that get_entities_by_topic with invalid kind raises error."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)

    with pytest.raises(ValueError, match="must be PUBLISHER or SUBSCRIBER"):
        graph.get_entities_by_topic(zrm.EntityKind.SERVICE, "test/topic")

    graph.close()


def test_graph_get_entities_by_service(context):
    """Test getting entities by service."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.ServiceServer(
        context,
        node_entity,
        "test_service",
        example_services_pb2.AddTwoInts,
        handler,
    )
    client = zrm.ServiceClient(
        context,
        node_entity,
        "test_service",
        example_services_pb2.AddTwoInts,
    )
    time.sleep(0.5)

    # Get services
    services = graph.get_entities_by_service(zrm.EntityKind.SERVICE, "test_service")
    assert len(services) >= 1

    # Get clients
    clients = graph.get_entities_by_service(zrm.EntityKind.CLIENT, "test_service")
    assert len(clients) >= 1

    server.close()
    client.close()
    graph.close()


def test_graph_get_entities_by_service_invalid_kind(context):
    """Test that get_entities_by_service with invalid kind raises error."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)

    with pytest.raises(ValueError, match="must be SERVICE or CLIENT"):
        graph.get_entities_by_service(zrm.EntityKind.PUBLISHER, "test_service")

    graph.close()


def test_graph_get_node_names(context):
    """Test getting all node names."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    node1 = zrm.Node("node1", context=context)
    node2 = zrm.Node("node2", context=context)
    time.sleep(0.5)

    names = graph.get_node_names()
    assert "node1" in names
    assert "node2" in names

    node1.close()
    node2.close()
    graph.close()


def test_graph_get_topic_names_and_types(context):
    """Test getting all topic names and types."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    pub = zrm.Publisher(context, node_entity, "robot/pose", geometry_pb2.Pose)
    time.sleep(0.5)

    topics = graph.get_topic_names_and_types()
    topic_dict = dict(topics)

    assert "robot/pose" in topic_dict
    assert topic_dict["robot/pose"] == "zrm.Pose"

    pub.close()
    graph.close()


def test_graph_get_service_names_and_types(context):
    """Test getting all service names and types."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.ServiceServer(
        context,
        node_entity,
        "add_service",
        example_services_pb2.AddTwoInts,
        handler,
    )
    time.sleep(0.5)

    services = graph.get_service_names_and_types()
    service_dict = dict(services)

    assert "add_service" in service_dict
    assert service_dict["add_service"] == "zrm.AddTwoInts.Request"

    server.close()
    graph.close()


def test_graph_get_entities_by_node(context):
    """Test getting entities by node."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    pub = zrm.Publisher(context, node_entity, "topic1", geometry_pb2.Pose)
    sub = zrm.Subscriber(context, node_entity, "topic2", geometry_pb2.Pose)
    time.sleep(0.5)

    # Get publishers for this node
    publishers = graph.get_entities_by_node(zrm.EntityKind.PUBLISHER, "test_node")
    assert len(publishers) >= 1

    # Get subscribers for this node
    subscribers = graph.get_entities_by_node(zrm.EntityKind.SUBSCRIBER, "test_node")
    assert len(subscribers) >= 1

    pub.close()
    sub.close()
    graph.close()


def test_graph_get_entities_by_node_invalid_kind(context):
    """Test that get_entities_by_node with NODE kind raises error."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)

    with pytest.raises(ValueError, match="must not be NODE"):
        graph.get_entities_by_node(zrm.EntityKind.NODE, "test_node")

    graph.close()


def test_graph_get_names_and_types_by_node(context):
    """Test getting names and types by node."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    graph = zrm.Graph(context.session, domain_id=context.domain_id)
    time.sleep(0.5)

    pub = zrm.Publisher(context, node_entity, "topic1", geometry_pb2.Pose)
    sub = zrm.Publisher(context, node_entity, "topic2", geometry_pb2.Point)
    time.sleep(0.5)

    # Get publisher topics for this node
    topics = graph.get_names_and_types_by_node("test_node", zrm.EntityKind.PUBLISHER)
    topic_names = [name for name, _ in topics]

    assert "topic1" in topic_names
    assert "topic2" in topic_names

    pub.close()
    sub.close()
    graph.close()


def test_graph_get_names_and_types_by_node_invalid_kind(context):
    """Test that get_names_and_types_by_node with NODE kind raises error."""
    graph = zrm.Graph(context.session, domain_id=context.domain_id)

    with pytest.raises(ValueError, match="must not be NODE"):
        graph.get_names_and_types_by_node("test_node", zrm.EntityKind.NODE)

    graph.close()


def test_graph_multiple_domains_isolated(context):
    """Test that graphs with different domain IDs are isolated."""
    ctx1 = zrm.Context(domain_id=1)
    ctx2 = zrm.Context(domain_id=2)

    node_entity1 = zrm.NodeEntity(
        domain_id=1,
        z_id=str(ctx1.session.info.zid()),
        name="node1",
    )
    node_entity2 = zrm.NodeEntity(
        domain_id=2,
        z_id=str(ctx2.session.info.zid()),
        name="node2",
    )

    graph1 = zrm.Graph(ctx1.session, domain_id=1)
    graph2 = zrm.Graph(ctx2.session, domain_id=2)
    time.sleep(0.5)

    # Create publisher in domain 1
    pub1 = zrm.Publisher(ctx1, node_entity1, "test/topic", geometry_pb2.Pose)
    time.sleep(0.5)

    # Domain 1 should see the publisher
    count1 = graph1.count(zrm.EntityKind.PUBLISHER, "test/topic")
    assert count1 >= 1

    # Domain 2 should NOT see the publisher
    count2 = graph2.count(zrm.EntityKind.PUBLISHER, "test/topic")
    assert count2 == 0

    pub1.close()
    graph1.close()
    graph2.close()
    ctx1.close()
    ctx2.close()


def test_graph_data_insert_remove():
    """Test GraphData insert and remove operations."""
    data = zrm.GraphData()

    # Insert keys
    data.insert("@zrm_lv/0/abc/NN/node1")
    data.insert("@zrm_lv/0/abc/MP/node1/topic1/type1")

    assert len(data._entities) == 2

    # Remove key
    data.remove("@zrm_lv/0/abc/NN/node1")
    assert len(data._entities) == 1

    # Remove non-existent key (should not raise)
    data.remove("nonexistent")


def test_graph_data_immediate_indexing():
    """Test GraphData immediate indexing on insert."""
    data = zrm.GraphData()

    # Insert keys
    data.insert("@zrm_lv/0/abc/NN/node1")
    data.insert("@zrm_lv/0/abc/MP/node1/topic1/geometry.Pose")

    # Entities should be stored
    assert len(data._entities) == 2

    # Indexes should be built immediately
    assert "topic1" in data._by_topic
    assert "node1" in data._by_node
