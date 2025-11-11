#!/usr/bin/env python3
"""Example service client that calls the add_two_ints service."""

import time

import zrm
from zrm import Node
from zrm.generated_protos import example_services_pb2


def main():
    # Create node
    node = Node("service_client_node")

    # Create service client via node factory method
    client = node.create_client(
        "add_two_ints",
        example_services_pb2.AddTwoInts,
    )
    print("Service client ready")
    print("Calling service every 2 seconds... (Ctrl+C to exit)")

    count = 0
    try:
        while True:
            # Create request
            request = example_services_pb2.AddTwoInts.Request(a=count, b=count * 2)

            # Call service
            print(f"Calling service: {request.a} + {request.b}")
            response = client.call(request)
            print(f"Response: {response.sum}\n")

            count += 1
            time.sleep(2)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        client.close()
        node.close()
        zrm.shutdown()


if __name__ == "__main__":
    main()
