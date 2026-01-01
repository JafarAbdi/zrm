#!/usr/bin/env python3
"""Example async service client with cancellation support.

This example demonstrates:
1. Async service calls with polling
2. Cancelling long-running service calls

Run the slow service server first:
    uv run python examples/slow_trigger_server.py

Then run this client:
    uv run python examples/async_service_client.py
"""

import time

import zrm
from zrm.srvs import std_pb2 as std_srvs


def main():
    node = zrm.Node("async_service_client_node")
    client = node.create_client("slow_trigger", std_srvs.Trigger)

    print("Waiting for slow_trigger service...")
    if not node.graph.wait_for_service("slow_trigger", timeout=5.0):
        print("Service not available. Run slow_trigger_server.py first.")
        client.close()
        node.close()
        zrm.shutdown()
        return

    print("Service available!\n")

    # Example 1: Let the slow call complete
    print("--- Example 1: Waiting for slow service to complete ---")
    request = std_srvs.Trigger.Request()
    future = client.call_async(request, timeout=30.0)

    print("Call started (service takes 5 seconds)...")
    start = time.time()
    while not future.done():
        elapsed = time.time() - start
        print(f"  Working... ({elapsed:.1f}s elapsed)")
        time.sleep(0.5)

    try:
        response = future.result()
        print(f"Result: success={response.success}, message='{response.message}'")
    except zrm.ServiceCancelled:
        print("Call was cancelled")
    except zrm.ServiceError as e:
        print(f"Service error: {e}")

    # Example 2: Cancel the slow call before it completes
    print("\n--- Example 2: Cancelling slow service after 2 seconds ---")
    future = client.call_async(request, timeout=30.0)

    print("Call started, will cancel in 2 seconds...")
    time.sleep(2.0)

    if future.cancel():
        print("Cancellation requested!")
    else:
        print("Already completed, couldn't cancel")

    try:
        response = future.result(timeout=1.0)
        print(f"Result: success={response.success}, message='{response.message}'")
    except zrm.ServiceCancelled:
        print("Call was cancelled (expected)")
    except TimeoutError:
        print("Timed out waiting for result")

    # Cleanup
    client.close()
    node.close()
    zrm.shutdown()
    print("\nDone!")


if __name__ == "__main__":
    main()
