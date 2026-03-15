#!/usr/bin/env python3
"""Example service client that calls the add_two_ints service."""

import time

import zrm
from zrm.srvs import examples_pb2


def main():
    with zrm.open(name="service_client") as session:
        client = zrm.Client(session, "add_two_ints", examples_pb2.AddTwoInts)
        print("Service client ready")
        print("Calling service every 2 seconds... (Ctrl+C to exit)")

        count = 0
        try:
            while True:
                request = examples_pb2.AddTwoInts.Request(a=count, b=count * 2)

                print(f"Calling service: {request.a} + {request.b}")
                response = client.call(request, timeout=5.0)
                print(f"Response: {response.sum}\n")

                count += 1
                time.sleep(2)

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            client.close()


if __name__ == "__main__":
    main()
