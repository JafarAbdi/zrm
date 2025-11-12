"""Tests for ServiceServer and ServiceClient classes."""

from __future__ import annotations

import time

import pytest

import zrm
from zrm.generated_protos import example_services_pb2, geometry_pb2


def test_service_server_creation(context):
    """Test creating a service server."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.ServiceServer(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        handler,
    )

    assert server._service == "add_two_ints"
    assert server._request_type == example_services_pb2.AddTwoInts.Request
    assert server._response_type == example_services_pb2.AddTwoInts.Response

    server.close()


def test_service_server_invalid_type_no_request(context):
    """Test that service server rejects type without Request message."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    def handler(req):
        return geometry_pb2.Pose()

    # geometry_pb2.Pose doesn't have Request/Response nested messages
    with pytest.raises(TypeError, match="must have a nested 'Request' message"):
        zrm.ServiceServer(
            context,
            node_entity,
            "invalid_service",
            geometry_pb2.Pose,
            handler,
        )


def test_service_client_creation(context):
    """Test creating a service client."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    assert client._service == "add_two_ints"
    assert client._request_type == example_services_pb2.AddTwoInts.Request
    assert client._response_type == example_services_pb2.AddTwoInts.Response

    client.close()


def test_service_client_invalid_type_no_response(context):
    """Test that service client rejects type without Response message."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    # geometry_pb2.Pose doesn't have Request/Response nested messages
    with pytest.raises(TypeError, match="must have a nested 'Request' message"):
        zrm.ServiceClient(
            context,
            node_entity,
            "invalid_service",
            geometry_pb2.Pose,
        )


def test_service_call_success(context):
    """Test successful service call."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.ServiceServer(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        handler,
    )
    time.sleep(0.2)  # Wait for server to be ready

    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    request = example_services_pb2.AddTwoInts.Request(a=5, b=7)
    response = client.call(request, timeout=2.0)

    assert response.sum == 12

    client.close()
    server.close()


def test_service_call_wrong_request_type(context):
    """Test service call with wrong request type raises TypeError."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    # Try to call with wrong type
    wrong_request = geometry_pb2.Pose()

    with pytest.raises(
        TypeError,
        match="Expected request of type Request",
    ):
        client.call(wrong_request, timeout=2.0)

    client.close()


def test_service_call_timeout(context):
    """Test service call timeout when no server available."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    client = zrm.ServiceClient(
        context,
        node_entity,
        "nonexistent_service",
        example_services_pb2.AddTwoInts,
    )

    request = example_services_pb2.AddTwoInts.Request(a=5, b=7)

    with pytest.raises(
        TimeoutError,
        match="did not respond within",
    ):
        client.call(request, timeout=0.5)

    client.close()


def test_service_handler_returns_wrong_type(context):
    """Test that service handler returning wrong type causes error."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    def bad_handler(req):
        # Return wrong type
        return geometry_pb2.Pose()

    server = zrm.ServiceServer(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        bad_handler,
    )
    time.sleep(0.2)

    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    request = example_services_pb2.AddTwoInts.Request(a=5, b=7)

    with pytest.raises(zrm.ServiceError, match="Service error"):
        client.call(request, timeout=2.0)

    client.close()
    server.close()


def test_service_handler_raises_exception(context):
    """Test that service handler exceptions are caught and returned as errors."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    def failing_handler(req):
        raise ValueError("Intentional error")

    server = zrm.ServiceServer(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        failing_handler,
    )
    time.sleep(0.2)

    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    request = example_services_pb2.AddTwoInts.Request(a=5, b=7)

    with pytest.raises(zrm.ServiceError, match="Service error"):
        client.call(request, timeout=2.0)

    client.close()
    server.close()


def test_multiple_service_calls(context):
    """Test multiple sequential service calls."""
    node_entity = zrm.NodeEntity(
        domain_id=context.domain_id,
        z_id=str(context.session.info.zid()),
        name="test_node",
    )

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.ServiceServer(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        handler,
    )
    time.sleep(0.2)

    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    # Make multiple calls
    for i in range(5):
        request = example_services_pb2.AddTwoInts.Request(a=i, b=i * 2)
        response = client.call(request, timeout=2.0)
        assert response.sum == i + (i * 2)

    client.close()
    server.close()


def test_service_liveliness_registration(context):
    """Test that service and client register with liveliness."""
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
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        handler,
    )
    client = zrm.ServiceClient(
        context,
        node_entity,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )
    time.sleep(0.5)

    # Check that both appear in graph
    server_count = graph.count(zrm.EntityKind.SERVICE, "add_two_ints")
    client_count = graph.count(zrm.EntityKind.CLIENT, "add_two_ints")

    assert server_count >= 1
    assert client_count >= 1

    client.close()
    server.close()
    graph.close()


def test_multiple_servers_same_service(context):
    """Test multiple servers handling the same service (load balancing)."""
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

    def handler(req):
        return example_services_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server1 = zrm.ServiceServer(
        context,
        node_entity1,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        handler,
    )
    server2 = zrm.ServiceServer(
        context,
        node_entity2,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        handler,
    )
    time.sleep(0.2)

    client = zrm.ServiceClient(
        context,
        node_entity1,
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )

    # Call should succeed (one of the servers will handle it)
    request = example_services_pb2.AddTwoInts.Request(a=5, b=7)
    response = client.call(request, timeout=2.0)
    assert response.sum == 12

    client.close()
    server1.close()
    server2.close()
