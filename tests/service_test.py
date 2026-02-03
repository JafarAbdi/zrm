"""Tests for Server and Client (service pattern)."""

from __future__ import annotations

import threading
import time

import pytest

import zrm
from zrm.srvs import examples_pb2


def test_server_creation(session):
    """Test creating a service server."""
    def handler(req):
        return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.Server(session, "add_service", examples_pb2.AddTwoInts, handler)
    assert server is not None
    server.close()


def test_server_invalid_name():
    """Test that server rejects name starting with /."""
    with zrm.open() as session:
        def handler(req):
            return examples_pb2.AddTwoInts.Response(sum=0)

        with pytest.raises(ValueError, match="cannot start with '/'"):
            zrm.Server(session, "/add_service", examples_pb2.AddTwoInts, handler)


def test_client_creation(session):
    """Test creating a service client."""
    client = zrm.Client(session, "add_service", examples_pb2.AddTwoInts)
    assert client is not None
    client.close()


def test_client_invalid_name():
    """Test that client rejects name starting with /."""
    with zrm.open() as session:
        with pytest.raises(ValueError, match="cannot start with '/'"):
            zrm.Client(session, "/add_service", examples_pb2.AddTwoInts)


def test_service_workflow(session):
    """Test complete service workflow."""
    def handler(req):
        return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.Server(session, "add_service", examples_pb2.AddTwoInts, handler)
    time.sleep(0.2)

    client = zrm.Client(session, "add_service", examples_pb2.AddTwoInts)

    request = examples_pb2.AddTwoInts.Request(a=10, b=20)
    response = client.call(request, timeout=2.0)

    assert response.sum == 30

    client.close()
    server.close()


def test_service_timeout():
    """Test service call timeout when no server."""
    with zrm.open() as session:
        client = zrm.Client(session, "nonexistent_service", examples_pb2.AddTwoInts)

        request = examples_pb2.AddTwoInts.Request(a=1, b=2)
        with pytest.raises(TimeoutError):
            client.call(request, timeout=0.5)

        client.close()


def test_client_type_validation(session):
    """Test that client validates request type."""
    def handler(req):
        return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.Server(session, "add_service", examples_pb2.AddTwoInts, handler)
    time.sleep(0.2)

    client = zrm.Client(session, "add_service", examples_pb2.AddTwoInts)

    # Wrong request type should raise.
    with pytest.raises(TypeError, match="Expected Request, got Response"):
        client.call(examples_pb2.AddTwoInts.Response(sum=0), timeout=2.0)

    client.close()
    server.close()


def test_concurrent_service_calls(session):
    """Test multiple concurrent service calls."""
    call_count = 0
    lock = threading.Lock()

    def handler(req):
        nonlocal call_count
        with lock:
            call_count += 1
        time.sleep(0.05)  # Simulate work.
        return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.Server(session, "compute", examples_pb2.AddTwoInts, handler)
    time.sleep(0.2)

    client = zrm.Client(session, "compute", examples_pb2.AddTwoInts)

    results = []
    errors = []

    def make_call(a, b):
        try:
            request = examples_pb2.AddTwoInts.Request(a=a, b=b)
            response = client.call(request, timeout=5.0)
            with lock:
                results.append(response.sum)
        except Exception as e:
            with lock:
                errors.append(e)

    # Make concurrent calls.
    threads = [threading.Thread(target=make_call, args=(i, i * 2)) for i in range(5)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 5
    assert call_count == 5

    # Verify results: i + i*2 for i in range(5) = [0, 3, 6, 9, 12]
    assert sorted(results) == [0, 3, 6, 9, 12]

    client.close()
    server.close()


def test_chained_service_calls(session):
    """Test chained service calls."""
    def add_handler(req):
        return examples_pb2.AddTwoInts.Response(sum=req.a + req.b)

    server = zrm.Server(session, "add", examples_pb2.AddTwoInts, add_handler)
    time.sleep(0.2)

    client = zrm.Client(session, "add", examples_pb2.AddTwoInts)

    # Make chained calls.
    result1 = client.call(examples_pb2.AddTwoInts.Request(a=1, b=2), timeout=2.0)
    result2 = client.call(examples_pb2.AddTwoInts.Request(a=result1.sum, b=3), timeout=2.0)
    result3 = client.call(examples_pb2.AddTwoInts.Request(a=result2.sum, b=4), timeout=2.0)

    # 1 + 2 = 3, 3 + 3 = 6, 6 + 4 = 10
    assert result3.sum == 10

    client.close()
    server.close()


def test_invalid_service_type():
    """Test that invalid service type raises TypeError."""
    with zrm.open() as session:
        # Missing Request.
        class BadService1:
            class Response:
                pass

        with pytest.raises(TypeError, match="must have nested 'Request' class"):
            zrm.Server(session, "bad", BadService1, lambda r: None)

        # Missing Response.
        class BadService2:
            class Request:
                pass

        with pytest.raises(TypeError, match="must have nested 'Response' class"):
            zrm.Server(session, "bad", BadService2, lambda r: None)
