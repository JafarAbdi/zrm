#!/usr/bin/env python3
"""CLI tool for inspecting ZRM services."""

from zrm import EntityKind, Node


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
    node = Node("_zrm_cli_service")

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
        servers = node.graph.get_entities_by_service(EntityKind.SERVICE, service_name)
        if servers:
            server_nodes = [
                e.endpoint.node.name for e in servers if e.endpoint is not None
            ]
            server_count = len(server_nodes)
            print(
                f"  Servers: {Color.GREEN}{server_count}{Color.RESET} {Color.DIM}{server_nodes}{Color.RESET}"
            )

        # Get service clients for this service
        clients = node.graph.get_entities_by_service(EntityKind.CLIENT, service_name)
        if clients:
            client_nodes = [
                e.endpoint.node.name for e in clients if e.endpoint is not None
            ]
            client_count = len(client_nodes)
            print(
                f"  Clients: {Color.YELLOW}{client_count}{Color.RESET} {Color.DIM}{client_nodes}{Color.RESET}"
            )

        print()  # Empty line between services

    node.close()


def main():
    """Main entry point for zrm-service CLI."""
    list_services()


if __name__ == "__main__":
    main()
