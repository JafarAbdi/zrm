#!/usr/bin/env python3
"""CLI tool for inspecting ZRM topics."""

import argparse
import sys
import time

from google.protobuf import text_format

from zrm import EntityKind, Node, get_message_type


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


def get_topic_type_from_graph(node: Node, topic: str) -> str:
    """Get the message type for a topic from the graph.

    Args:
        node: Node instance with graph access
        topic: Topic name

    Returns:
        Full protobuf type name

    Raises:
        ValueError: If topic is not found in the graph
    """
    topics = node.graph.get_topic_names_and_types()
    for topic_name, type_name in topics:
        if topic_name == topic:
            return type_name

    raise ValueError(f"Topic '{topic}' not found in the network")


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


def pub_topic(topic: str, msg_type_name: str | None, data: str, rate: float):
    """Publish messages to a topic.

    Args:
        topic: Topic name to publish to
        msg_type_name: Protobuf message type name (auto-discovered if None)
        data: Message data in protobuf text format
        rate: Publishing rate in Hz
    """
    node = Node("_zrm_cli_pub")

    # Auto-discover type if not provided
    if msg_type_name is None:
        try:
            msg_type_name = get_topic_type_from_graph(node, topic)
            print(f"{Color.DIM}Auto-discovered type: {msg_type_name}{Color.RESET}")
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
            print(
                f"{Color.YELLOW}Hint: Topic not found. You must specify the type with --type{Color.RESET}"
            )
            node.close()
            sys.exit(1)

    try:
        msg_type = get_message_type(msg_type_name)
    except (ImportError, AttributeError, ValueError) as e:
        print(f"{Color.RED}Error loading message type: {e}{Color.RESET}")
        print(
            f"{Color.YELLOW}Hint: Type format should be 'package/category/module/Type' (e.g., 'zrm/msgs/geometry/Pose2D'){Color.RESET}"
        )
        node.close()
        sys.exit(1)

    # Parse the message from text format
    msg = msg_type()
    try:
        text_format.Parse(data, msg)
    except text_format.ParseError as e:
        print(f"{Color.RED}Error parsing message data: {e}{Color.RESET}")
        node.close()
        sys.exit(1)

    # Create publisher
    pub = node.create_publisher(topic, msg_type)

    print(
        f"{Color.GREEN}Publishing to {Color.BOLD}{topic}{Color.RESET}{Color.GREEN} at {rate} Hz{Color.RESET}"
    )
    print(f"{Color.DIM}Press Ctrl+C to stop{Color.RESET}\n")

    try:
        interval = 1.0 / rate
        while True:
            pub.publish(msg)
            print(
                f"{Color.DIM}Published: {text_format.MessageToString(msg, as_one_line=True)}{Color.RESET}"
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}Stopped publishing{Color.RESET}")
    finally:
        pub.close()
        node.close()


def echo_topic(topic: str, msg_type_name: str | None):
    """Echo messages from a topic.

    Args:
        topic: Topic name to subscribe to
        msg_type_name: Protobuf message type name (auto-discovered if None)
    """
    node = Node("_zrm_cli_echo")

    # Auto-discover type if not provided
    if msg_type_name is None:
        try:
            msg_type_name = get_topic_type_from_graph(node, topic)
            print(f"{Color.DIM}Auto-discovered type: {msg_type_name}{Color.RESET}\n")
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
            print(
                f"{Color.YELLOW}Hint: Topic not found. You must specify the type with --type{Color.RESET}"
            )
            node.close()
            sys.exit(1)

    try:
        msg_type = get_message_type(msg_type_name)
    except (ImportError, AttributeError, ValueError) as e:
        print(f"{Color.RED}Error loading message type: {e}{Color.RESET}")
        print(
            f"{Color.YELLOW}Hint: Type format should be 'package/category/module/Type' (e.g., 'zrm/msgs/geometry/Pose2D'){Color.RESET}"
        )
        node.close()
        sys.exit(1)

    def callback(msg):
        print(f"{Color.CYAN}{topic}:{Color.RESET}")
        # Use text_format to print all fields including defaults
        print(f"{Color.DIM}{text_format.MessageToString(msg)}{Color.RESET}")

    sub = node.create_subscriber(topic, msg_type, callback=callback)

    print(
        f"{Color.GREEN}Listening to {Color.BOLD}{topic}{Color.RESET}{Color.GREEN} [{msg_type_name}]{Color.RESET}"
    )
    print(f"{Color.DIM}Press Ctrl+C to stop{Color.RESET}\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}Stopped listening{Color.RESET}")
    finally:
        sub.close()
        node.close()


def hz_topic(topic: str, msg_type_name: str | None, window: int):
    """Measure message frequency on a topic.

    Args:
        topic: Topic name to measure
        msg_type_name: Protobuf message type name (auto-discovered if None)
        window: Window size for averaging (number of messages)
    """
    node = Node("_zrm_cli_hz")

    # Auto-discover type if not provided
    if msg_type_name is None:
        try:
            msg_type_name = get_topic_type_from_graph(node, topic)
            print(f"{Color.DIM}Auto-discovered type: {msg_type_name}{Color.RESET}\n")
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
            print(
                f"{Color.YELLOW}Hint: Topic not found. You must specify the type with --type{Color.RESET}"
            )
            node.close()
            sys.exit(1)

    try:
        msg_type = get_message_type(msg_type_name)
    except (ImportError, AttributeError, ValueError) as e:
        print(f"{Color.RED}Error loading message type: {e}{Color.RESET}")
        print(
            f"{Color.YELLOW}Hint: Type format should be 'package/category/module/Type' (e.g., 'zrm/msgs/geometry/Pose2D'){Color.RESET}"
        )
        node.close()
        sys.exit(1)

    timestamps = []

    def callback(msg):
        timestamps.append(time.time())
        if len(timestamps) > window:
            timestamps.pop(0)

        if len(timestamps) >= 2:
            time_span = timestamps[-1] - timestamps[0]
            msg_count = len(timestamps) - 1
            hz = msg_count / time_span if time_span > 0 else 0
            print(
                f"{Color.CYAN}Rate: {Color.BOLD}{hz:.2f} Hz{Color.RESET} {Color.DIM}(avg over {msg_count} messages){Color.RESET}"
            )

    sub = node.create_subscriber(topic, msg_type, callback=callback)

    print(
        f"{Color.GREEN}Measuring rate on {Color.BOLD}{topic}{Color.RESET}{Color.GREEN} [{msg_type_name}]{Color.RESET}"
    )
    print(f"{Color.DIM}Press Ctrl+C to stop{Color.RESET}\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}Stopped measuring{Color.RESET}")
    finally:
        sub.close()
        node.close()


def main():
    """Main entry point for zrm-topic CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM topic inspection and interaction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all topics in the network")

    # Pub command
    pub_parser = subparsers.add_parser("pub", help="Publish messages to a topic")
    pub_parser.add_argument("topic", help="Topic name")
    pub_parser.add_argument("data", help="Message data in protobuf text format")
    pub_parser.add_argument(
        "-t",
        "--type",
        dest="msg_type",
        help="Message type (e.g., zrm/msgs/geometry/Pose2D). Auto-discovered if not specified.",
    )
    pub_parser.add_argument(
        "-r",
        "--rate",
        type=float,
        default=1.0,
        help="Publishing rate in Hz (default: 1.0)",
    )

    # Echo command
    echo_parser = subparsers.add_parser("echo", help="Echo messages from a topic")
    echo_parser.add_argument("topic", help="Topic name")
    echo_parser.add_argument(
        "-t",
        "--type",
        dest="msg_type",
        help="Message type (e.g., zrm/msgs/geometry/Pose2D). Auto-discovered if not specified.",
    )

    # Hz command
    hz_parser = subparsers.add_parser("hz", help="Measure message frequency on a topic")
    hz_parser.add_argument("topic", help="Topic name")
    hz_parser.add_argument(
        "-t",
        "--type",
        dest="msg_type",
        help="Message type (e.g., zrm/msgs/geometry/Pose2D). Auto-discovered if not specified.",
    )
    hz_parser.add_argument(
        "-w",
        "--window",
        type=int,
        default=10,
        help="Window size for averaging (default: 10)",
    )

    args = parser.parse_args()

    match args.command:
        case "list":
            list_topics()
        case "pub":
            pub_topic(args.topic, args.msg_type, args.data, args.rate)
        case "echo":
            echo_topic(args.topic, args.msg_type)
        case "hz":
            hz_topic(args.topic, args.msg_type, args.window)
        case _:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
