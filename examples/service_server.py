#!/usr/bin/env python3
"""Example service server that adds two integers."""

import time

import zrm
from zrm.srvs import examples_pb2
from zrm.srvs import std_pb2


def add_callback(
    req: examples_pb2.AddTwoInts.Request,
) -> examples_pb2.AddTwoInts.Response:
    """Callback function that handles the service request."""
    result = req.a + req.b
    print(f"Request: {req.a} + {req.b} = {result}")
    return examples_pb2.AddTwoInts.Response(sum=result)


def trigger_callback(
    req: std_pb2.Trigger.Request,
) -> std_pb2.Trigger.Response:
    """Callback function that handles the trigger request."""
    print("Trigger received")
    return std_pb2.Trigger.Response(success=True, message="Triggered successfully")


def main():
    with zrm.open(name="service_server") as session:
        add_server = zrm.Server(
            session, "add_two_ints", examples_pb2.AddTwoInts, add_callback
        )
        trigger_server = zrm.Server(
            session, "trigger", std_pb2.Trigger, trigger_callback
        )

        print("Service servers started:")
        print("  - add_two_ints")
        print("  - trigger")
        print("Waiting for requests... (Ctrl+C to exit)")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            add_server.close()
            trigger_server.close()


if __name__ == "__main__":
    main()
