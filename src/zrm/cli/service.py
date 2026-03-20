#!/usr/bin/env python3
"""CLI tool for inspecting ZRM services."""

import argparse
import sys

import zrm
from zrm import cli


def list_services():
    """List all services in the ZRM network."""
    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        services = graph.get_services()

        if not services:
            print(f"{cli.Style.YELLOW}No services found in the network{cli.Style.R}")
            graph.close()
            return

        for service_name, type_name in sorted(services):
            print(f"{cli.Style.BOLD}{cli.Style.GREEN}{service_name}{cli.Style.R}")
            print(f"  Type: {cli.Style.DIM}{type_name}{cli.Style.R}")

            servers = graph.get_servers(service_name)
            if servers:
                names = [e.name for e in servers]
                print(
                    f"  Servers: {cli.Style.GREEN}{len(names)}{cli.Style.R} {cli.Style.DIM}{names}{cli.Style.R}"
                )

            clients = graph.get_clients(service_name)
            if clients:
                names = [e.name for e in clients]
                print(
                    f"  Clients: {cli.Style.YELLOW}{len(names)}{cli.Style.R} {cli.Style.DIM}{names}{cli.Style.R}"
                )

            print()

        graph.close()


def call_service(service: str, service_type_name: str | None, data: str):
    """Call a service with the given request data."""
    print(f"Calling {cli.Style.BOLD}{service}{cli.Style.R}")
    try:
        response = cli.call(service, data, service_type=service_type_name)
        print(response, end="")
    except TimeoutError:
        print(f"{cli.Style.RED}Timeout waiting for response{cli.Style.R}")
        sys.exit(1)
    except zrm.ServiceError as e:
        print(f"{cli.Style.RED}Service error: {e}{cli.Style.R}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{cli.Style.YELLOW}Interrupted{cli.Style.R}")
        sys.exit(130)


def main():
    """Main entry point for zrm-service CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM service inspection and interaction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    subparsers.add_parser("list", help="List all services in the network")

    call_parser = subparsers.add_parser("call", help="Call a service")
    call_parser.add_argument("service", help="Service name")
    call_parser.add_argument("data", help="Request data in protobuf text format")
    call_parser.add_argument(
        "-t",
        "--type",
        dest="service_type",
        help="Service type (e.g., zrm/srvs/examples/AddTwoInts). Auto-discovered if not specified.",
    )

    args = parser.parse_args()

    try:
        match args.command:
            case "list":
                list_services()
            case "call":
                call_service(args.service, args.service_type, args.data)
            case _:
                parser.print_help()
                sys.exit(1)
    except (ValueError, LookupError) as e:
        print(f"{cli.Style.RED}Error: {e}{cli.Style.R}")
        sys.exit(1)


if __name__ == "__main__":
    main()
