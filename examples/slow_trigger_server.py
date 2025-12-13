#!/usr/bin/env python3
"""Example slow service server for testing async cancellation.

This server simulates a long-running operation (5 seconds).
Use with async_service_client.py to test cancellation.

Usage:
    uv run python examples/slow_trigger_server.py
"""

import time

import zrm
from zrm import Node
from zrm.srvs import std_pb2 as std_srvs


def slow_trigger_callback(
    req: std_srvs.Trigger.Request,
) -> std_srvs.Trigger.Response:
    """Simulate a slow operation that takes 5 seconds."""
    print("Slow trigger received, working for 5 seconds...")
    time.sleep(5)
    print("Work complete!")
    return std_srvs.Trigger.Response(success=True, message="Completed after 5 seconds")


def main():
    node = Node("slow_trigger_server_node")

    server = node.create_service(
        "slow_trigger",
        std_srvs.Trigger,
        slow_trigger_callback,
    )

    print("Slow trigger server started (each call takes 5 seconds)")
    print("Waiting for requests... (Ctrl+C to exit)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
