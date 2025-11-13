#!/usr/bin/env python3
"""Example service server that adds two integers."""

import time

import zrm
from zrm import Node
from zrm.srvs import examples_pb2 as example_srvs
from zrm.srvs import std_pb2 as std_srvs


def add_callback(
    req: example_srvs.AddTwoInts.Request,
) -> example_srvs.AddTwoInts.Response:
    """Callback function that handles the service request."""
    result = req.a + req.b
    print(f"Request: {req.a} + {req.b} = {result}")
    return example_srvs.AddTwoInts.Response(sum=result)


def trigger_callback(
    req: std_srvs.Trigger.Request,
) -> std_srvs.Trigger.Response:
    """Callback function that handles the trigger request."""
    print("Trigger received")
    return std_srvs.Trigger.Response(success=True, message="Triggered successfully")


def main():
    # Create node
    node = Node("service_server_node")

    # Create service server via node factory method
    server = node.create_service(
        "add_two_ints",
        example_srvs.AddTwoInts,
        add_callback,
    )
    trigger_server = node.create_service(
        "trigger",
        std_srvs.Trigger,
        trigger_callback,
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
        zrm.shutdown()


if __name__ == "__main__":
    main()
