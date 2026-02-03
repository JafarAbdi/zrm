#!/usr/bin/env python3
"""CLI tool for inspecting ZRM services."""

import argparse
import sys

from google.protobuf import text_format

import zrm


class Style:
    """ANSI styles for terminal output."""

    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    R = "\033[0m"


def list_services():
    """List all services in the ZRM network."""
    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        services = graph.get_services()

        if not services:
            print(f"{Style.YELLOW}No services found in the network{Style.R}")
            graph.close()
            return

        for service_name, type_name in sorted(services):
            print(f"{Style.BOLD}{Style.GREEN}{service_name}{Style.R}")
            print(f"  Type: {Style.DIM}{type_name}{Style.R}")

            servers = graph.get_servers(service_name)
            if servers:
                names = [e.name for e in servers]
                print(
                    f"  Servers: {Style.GREEN}{len(names)}{Style.R} {Style.DIM}{names}{Style.R}"
                )

            clients = graph.get_clients(service_name)
            if clients:
                names = [e.name for e in clients]
                print(
                    f"  Clients: {Style.YELLOW}{len(names)}{Style.R} {Style.DIM}{names}{Style.R}"
                )

            print()

        graph.close()


def call_service(service: str, service_type_name: str | None, data: str):
    """Call a service with the given request data."""
    if service.startswith("/"):
        print(
            f"{Style.RED}Service name cannot start with '/'. Use '{service.lstrip('/')}' instead.{Style.R}"
        )
        sys.exit(1)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)

        # Auto-discover type if not provided.
        if service_type_name is None:
            for svc_name, type_name in graph.get_services():
                if svc_name == service:
                    service_type_name = type_name
                    print(f"{Style.DIM}Type: {service_type_name}{Style.R}")
                    break
            else:
                print(f"{Style.RED}Service '{service}' not found{Style.R}")
                print(f"{Style.YELLOW}Specify type with --type{Style.R}")
                graph.close()
                sys.exit(1)

        try:
            service_type = zrm.get_message_type(service_type_name)
        except (ImportError, AttributeError, ValueError) as e:
            print(f"{Style.RED}Error loading service type: {e}{Style.R}")
            graph.close()
            sys.exit(1)

        # Parse the request from text format.
        request = service_type.Request()
        try:
            text_format.Parse(data, request)
        except text_format.ParseError as e:
            print(f"{Style.RED}Error parsing request data: {e}{Style.R}")
            graph.close()
            sys.exit(1)

        # Show server info.
        servers = graph.get_servers(service)
        if servers:
            names = ", ".join(e.name for e in servers)
            print(f"{Style.DIM}Server: {names}{Style.R}")

        client = zrm.Client(session, service, service_type)

        print(f"Calling {Style.BOLD}{service}{Style.R}")
        print(
            f"{Style.DIM}Request: {text_format.MessageToString(request, as_one_line=True)}{Style.R}\n"
        )

        try:
            response = client.call(request, timeout=300.0)
            print(f"{text_format.MessageToString(response)}", end="")
        except TimeoutError:
            print(f"{Style.RED}Timeout waiting for response{Style.R}")
            sys.exit(1)
        except zrm.ServiceError as e:
            print(f"{Style.RED}Service error: {e}{Style.R}")
            sys.exit(1)
        except KeyboardInterrupt:
            print(f"\n{Style.YELLOW}Interrupted{Style.R}")
            sys.exit(130)
        finally:
            client.close()
            graph.close()


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
