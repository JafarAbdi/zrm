#!/usr/bin/env python3
"""CLI tool for inspecting ZRM topics."""

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


def list_topics():
    """List all topics in the ZRM network."""
    # Create a temporary node for graph access
    node = Node("_zrm_cli_topic")

    # Get all topics with their types
    topics = node.graph.get_topic_names_and_types()

    if not topics:
        print(f"{Color.YELLOW}No topics found in the network{Color.RESET}")
        node.close()
        return

    print(f"{Color.BOLD}{Color.CYAN}=== ZRM Topics ==={Color.RESET}\n")

    for topic_name, type_name in sorted(topics):
        print(f"{Color.BOLD}{Color.GREEN}{topic_name}{Color.RESET}")
        print(f"  Type: {Color.DIM}{type_name}{Color.RESET}")

        # Get publishers for this topic
        publishers = node.graph.get_entities_by_topic(EntityKind.PUBLISHER, topic_name)
        if publishers:
            pub_nodes = [e.node_name for e in publishers]
            pub_count = len(pub_nodes)
            print(
                f"  Publishers: {Color.CYAN}{pub_count}{Color.RESET} {Color.DIM}{pub_nodes}{Color.RESET}"
            )

        # Get subscribers for this topic
        subscribers = node.graph.get_entities_by_topic(
            EntityKind.SUBSCRIBER, topic_name
        )
        if subscribers:
            sub_nodes = [e.node_name for e in subscribers]
            sub_count = len(sub_nodes)
            print(
                f"  Subscribers: {Color.BLUE}{sub_count}{Color.RESET} {Color.DIM}{sub_nodes}{Color.RESET}"
            )

        print()  # Empty line between topics

    node.close()


def main():
    """Main entry point for zrm-topic CLI."""
    list_topics()


if __name__ == "__main__":
    main()
