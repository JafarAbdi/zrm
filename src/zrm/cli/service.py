#!/usr/bin/env python3
"""CLI tool for inspecting ZRM services."""

import argparse
import sys

from google.protobuf import text_format

import zrm


# ANSI color codes
class Color:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


def list_services():
    """List all services in the ZRM network."""
    # Create a temporary node for graph access
    node = zrm.Node("_zrm_cli_service")

    # Get all services with their types
    services = node.graph.get_service_names_and_types()

    if not services:
        print(f"{Color.YELLOW}No services found in the network{Color.RESET}")
        node.close()
        return

    print(f"{Color.BOLD}{Color.CYAN}=== ZRM Services ==={Color.RESET}\n")

    for service_name, type_name in sorted(services):
        print(f"{Color.BOLD}{Color.GREEN}{service_name}{Color.RESET}")
        print(f"  Type: {Color.DIM}{type_name}{Color.RESET}")

        # Get service servers for this service
        servers = node.graph.get_entities_by_service(
            zrm.EntityKind.SERVICE, service_name
        )
        if servers:
            server_nodes = [e.node_name for e in servers]
            server_count = len(server_nodes)
            print(
                f"  Servers: {Color.GREEN}{server_count}{Color.RESET} {Color.DIM}{server_nodes}{Color.RESET}"
            )

        # Get service clients for this service
        clients = node.graph.get_entities_by_service(
            zrm.EntityKind.CLIENT, service_name
        )
        if clients:
            client_nodes = [e.node_name for e in clients]
            client_count = len(client_nodes)
            print(
                f"  Clients: {Color.YELLOW}{client_count}{Color.RESET} {Color.DIM}{client_nodes}{Color.RESET}"
            )

        print()  # Empty line between services

    node.close()


def call_service(service: str, service_type_name: str | None, data: str):
    """Call a service with the given request data.

    Args:
        service: Service name to call
        service_type_name: Protobuf service type name (auto-discovered if None)
        data: Request data in protobuf text format
    """
    node = zrm.Node("_zrm_cli_call")

    # Auto-discover type if not provided
    if service_type_name is None:
        try:
            services = node.graph.get_service_names_and_types()
            for svc_name, type_name in services:
                if svc_name == service:
                    service_type_name = type_name
                    print(
                        f"{Color.DIM}Auto-discovered type: {service_type_name}{Color.RESET}"
                    )
                    break
            else:
                raise ValueError(f"Service '{service}' not found in the network")
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
            print(
                f"{Color.YELLOW}Hint: Service not found. You must specify the type with --type{Color.RESET}"
            )
            node.close()
            sys.exit(1)

    try:
        service_type = zrm.get_message_type(service_type_name)
    except (ImportError, AttributeError, ValueError) as e:
        print(f"{Color.RED}Error loading service type: {e}{Color.RESET}")
        print(
            f"{Color.YELLOW}Hint: Type format should be 'package/category/module/Type' (e.g., 'zrm/srvs/example/AddTwoInts'){Color.RESET}"
        )
        node.close()
        sys.exit(1)

    # Parse the request from text format
    request = service_type.Request()
    try:
        text_format.Parse(data, request)
    except text_format.ParseError as e:
        print(f"{Color.RED}Error parsing request data: {e}{Color.RESET}")
        node.close()
        sys.exit(1)

    # Create client and call service
    client = node.create_client(service, service_type)

    print(
        f"{Color.GREEN}Calling service {Color.BOLD}{service}{Color.RESET}{Color.GREEN} [{service_type_name}]{Color.RESET}"
    )
    print(
        f"{Color.DIM}Request: {text_format.MessageToString(request, as_one_line=True)}{Color.RESET}\n"
    )

    try:
        response = client.call(request)
        print(f"{Color.CYAN}Response:{Color.RESET}")
        print(f"{Color.DIM}{text_format.MessageToString(response)}{Color.RESET}")
    except Exception as e:
        print(f"{Color.RED}Error calling service: {e}{Color.RESET}")
        sys.exit(1)
    finally:
        client.close()
        node.close()


def main():
    """Main entry point for zrm-service CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM service inspection and interaction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all services in the network")

    # Call command
    call_parser = subparsers.add_parser("call", help="Call a service")
    call_parser.add_argument("service", help="Service name")
    call_parser.add_argument("data", help="Request data in protobuf text format")
    call_parser.add_argument(
        "-t",
        "--type",
        dest="service_type",
        help="Service type (e.g., zrm/srvs/example/AddTwoInts). Auto-discovered if not specified.",
    )

    args = parser.parse_args()

    match args.command:
        case "list":
            list_services()
        case "call":
            call_service(args.service, args.service_type, args.data)
        case _:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
