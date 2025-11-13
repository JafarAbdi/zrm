#!/usr/bin/env python3
"""CLI tool for inspecting ZRM nodes."""

import argparse
import sys

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


def list_nodes():
    """List all nodes in the ZRM network."""
    # Create a temporary node for graph access
    node = zrm.Node("_zrm_cli_node")

    # Get all node names
    node_names = node.graph.get_node_names()

    if not node_names:
        print(f"{Color.YELLOW}No nodes found in the network{Color.RESET}")
        node.close()
        return

    print(f"{Color.BOLD}{Color.CYAN}=== ZRM Nodes ==={Color.RESET}\n")

    for node_name in sorted(node_names):
        print(f"{Color.BOLD}{Color.GREEN}Node: {node_name}{Color.RESET}")

        # Get publishers for this node
        publishers = node.graph.get_entities_by_node(
            zrm.EntityKind.PUBLISHER, node_name
        )
        if publishers:
            print(f"  {Color.CYAN}Publishers:{Color.RESET}")
            for pub in publishers:
                type_display = (
                    f"{Color.DIM}({pub.type_name}){Color.RESET}"
                    if pub.type_name
                    else ""
                )
                print(f"    • {pub.topic} {type_display}")

        # Get subscribers for this node
        subscribers = node.graph.get_entities_by_node(
            zrm.EntityKind.SUBSCRIBER, node_name
        )
        if subscribers:
            print(f"  {Color.BLUE}Subscribers:{Color.RESET}")
            for sub in subscribers:
                type_display = (
                    f"{Color.DIM}({sub.type_name}){Color.RESET}"
                    if sub.type_name
                    else ""
                )
                print(f"    • {sub.topic} {type_display}")

        # Get services for this node
        services = node.graph.get_entities_by_node(zrm.EntityKind.SERVICE, node_name)
        if services:
            print(f"  {Color.HEADER}Services:{Color.RESET}")
            for svc in services:
                type_display = (
                    f"{Color.DIM}({svc.type_name}){Color.RESET}"
                    if svc.type_name
                    else ""
                )
                print(f"    • {svc.topic} {type_display}")

        # Get clients for this node
        clients = node.graph.get_entities_by_node(zrm.EntityKind.CLIENT, node_name)
        if clients:
            print(f"  {Color.YELLOW}Clients:{Color.RESET}")
            for client in clients:
                type_display = (
                    f"{Color.DIM}({client.type_name}){Color.RESET}"
                    if client.type_name
                    else ""
                )
                print(f"    • {client.topic} {type_display}")

        print()  # Empty line between nodes

    node.close()


def main():
    """Main entry point for zrm-node CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM node inspection tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all nodes in the network")

    args = parser.parse_args()

    match args.command:
        case "list":
            list_nodes()
        case _:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
