#!/usr/bin/env python3
"""Example slow service server for testing long-running operations.

This server simulates a long-running operation (5 seconds).

Usage:
    uv run python examples/slow_trigger_server.py
"""

import time

import zrm
from zrm.srvs import std_pb2


def slow_trigger_callback(
    req: std_pb2.Trigger.Request,
) -> std_pb2.Trigger.Response:
    """Simulate a slow operation that takes 5 seconds."""
    print("Slow trigger received, working for 5 seconds...")
    time.sleep(5)
    print("Work complete!")
    return std_pb2.Trigger.Response(success=True, message="Completed after 5 seconds")


def main():
    with zrm.open(name="slow_trigger_server") as session:
        server = zrm.Server(
            session, "slow_trigger", std_pb2.Trigger, slow_trigger_callback
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


if __name__ == "__main__":
    main()
