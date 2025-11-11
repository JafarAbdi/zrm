#!/usr/bin/env python3
"""Example service server that adds two integers."""

import time

import zrm
from zrm import Node
from zrm.generated_protos import example_services_pb2


def add_callback(
    req: example_services_pb2.AddTwoInts.Request,
) -> example_services_pb2.AddTwoInts.Response:
    """Callback function that handles the service request."""
    result = req.a + req.b
    print(f"Request: {req.a} + {req.b} = {result}")
    return example_services_pb2.AddTwoInts.Response(sum=result)


def main():
    # Create node
    node = Node("service_server_node")

    # Create service server via node factory method
    server = node.create_service(
        "add_two_ints",
        example_services_pb2.AddTwoInts,
        add_callback,
    )
    print("Service server 'add_two_ints' started")
    print("Waiting for requests... (Ctrl+C to exit)")

    try:
        # Keep the server running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        server.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
