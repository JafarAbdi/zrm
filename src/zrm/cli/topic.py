#!/usr/bin/env python3
"""CLI tool for inspecting ZRM topics."""

import argparse
import sys
import time

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


def _discover_type(graph: zrm.Graph, topic: str) -> str | None:
    """Get the message type for a topic from the graph."""
    for topic_name, type_name in graph.get_topics():
        if topic_name == topic:
            return type_name
    return None


def _resolve_type(graph: zrm.Graph, topic: str, msg_type_name: str | None) -> str:
    """Resolve message type: use provided or auto-discover from graph."""
    if msg_type_name is not None:
        return msg_type_name

    discovered = _discover_type(graph, topic)
    if discovered is None:
        print(f"{Style.YELLOW}Topic not found. Specify type with --type{Style.R}")
        graph.close()
        sys.exit(1)

    print(f"{Style.DIM}Type: {discovered}{Style.R}")
    return discovered


def _load_msg_type(graph: zrm.Graph, type_name: str) -> type:
    """Load a protobuf message type by name, exit on failure."""
    try:
        return zrm.get_message_type(type_name)
    except (ImportError, AttributeError, ValueError) as e:
        print(f"{Style.RED}Error loading message type: {e}{Style.R}")
        graph.close()
        sys.exit(1)


def list_topics():
    """List all topics in the ZRM network."""
    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        topics = graph.get_topics()

        if not topics:
            print(f"{Style.YELLOW}No topics found in the network{Style.R}")
            graph.close()
            return

        for topic_name, type_name in sorted(topics):
            print(f"{Style.BOLD}{Style.GREEN}{topic_name}{Style.R}")
            print(f"  Type: {Style.DIM}{type_name}{Style.R}")

            publishers = graph.get_publishers(topic_name)
            if publishers:
                names = [e.name for e in publishers]
                print(
                    f"  Publishers: {Style.CYAN}{len(names)}{Style.R} {Style.DIM}{names}{Style.R}"
                )

            subscribers = graph.get_subscribers(topic_name)
            if subscribers:
                names = [e.name for e in subscribers]
                print(
                    f"  Subscribers: {Style.BLUE}{len(names)}{Style.R} {Style.DIM}{names}{Style.R}"
                )

            print()

        graph.close()


def pub_topic(topic: str, msg_type_name: str | None, data: str, rate: float):
    """Publish messages to a topic."""
    if topic.startswith("/"):
        print(
            f"{Style.RED}Topic cannot start with '/'. Use '{topic.lstrip('/')}' instead.{Style.R}"
        )
        sys.exit(1)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        msg_type_name = _resolve_type(graph, topic, msg_type_name)
        msg_type = _load_msg_type(graph, msg_type_name)

        msg = msg_type()
        try:
            text_format.Parse(data, msg)
        except text_format.ParseError as e:
            print(f"{Style.RED}Error parsing message data: {e}{Style.R}")
            graph.close()
            sys.exit(1)

        pub = zrm.Publisher(session, topic, msg_type)

        print(f"Publishing to {Style.BOLD}{topic}{Style.R} at {rate} Hz")

        try:
            interval = 1.0 / rate
            while True:
                pub.publish(msg)
                print(
                    f"{Style.DIM}{text_format.MessageToString(msg, as_one_line=True)}{Style.R}"
                )
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            pub.close()
            graph.close()


def echo_topic(topic: str, msg_type_name: str | None):
    """Echo messages from a topic."""
    if topic.startswith("/"):
        print(
            f"{Style.RED}Topic cannot start with '/'. Use '{topic.lstrip('/')}' instead.{Style.R}"
        )
        sys.exit(1)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        msg_type_name = _resolve_type(graph, topic, msg_type_name)
        msg_type = _load_msg_type(graph, msg_type_name)

        publishers = graph.get_publishers(topic)
        if publishers:
            names = ", ".join(e.name for e in publishers)
            print(f"{Style.DIM}Publishers: {names}{Style.R}")

        def callback(msg):
            print(f"{Style.BOLD}{topic}{Style.R}")
            print(f"{Style.DIM}{text_format.MessageToString(msg)}{Style.R}", end="")

        sub = zrm.Subscriber(session, topic, msg_type, callback=callback)

        print(f"Listening to {Style.BOLD}{topic}{Style.R}\n")

        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            sub.close()
            graph.close()


def hz_topic(topic: str, msg_type_name: str | None, window: int):
    """Measure message frequency on a topic."""
    if topic.startswith("/"):
        print(
            f"{Style.RED}Topic cannot start with '/'. Use '{topic.lstrip('/')}' instead.{Style.R}"
        )
        sys.exit(1)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        msg_type_name = _resolve_type(graph, topic, msg_type_name)
        msg_type = _load_msg_type(graph, msg_type_name)

        publishers = graph.get_publishers(topic)
        if publishers:
            names = ", ".join(e.name for e in publishers)
            print(f"{Style.DIM}Publishers: {names}{Style.R}")

        timestamps: list[float] = []

        def callback(msg):
            timestamps.append(time.time())
            if len(timestamps) > window:
                timestamps.pop(0)

            if len(timestamps) >= 2:
                time_span = timestamps[-1] - timestamps[0]
                msg_count = len(timestamps) - 1
                hz = msg_count / time_span if time_span > 0 else 0
                print(
                    f"  {Style.BOLD}{hz:.2f} Hz{Style.R}  {Style.DIM}(avg of {msg_count}){Style.R}"
                )

        sub = zrm.Subscriber(session, topic, msg_type, callback=callback)

        print(f"Measuring {Style.BOLD}{topic}{Style.R}\n")

        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            sub.close()
            graph.close()


def main():
    """Main entry point for zrm-topic CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM topic inspection and interaction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    subparsers.add_parser("list", help="List all topics in the network")

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

    echo_parser = subparsers.add_parser("echo", help="Echo messages from a topic")
    echo_parser.add_argument("topic", help="Topic name")
    echo_parser.add_argument(
        "-t",
        "--type",
        dest="msg_type",
        help="Message type (e.g., zrm/msgs/geometry/Pose2D). Auto-discovered if not specified.",
    )

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

    try:
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
    except Exception as e:
        print(f"{Style.RED}Error: {e}{Style.R}")
        sys.exit(1)


if __name__ == "__main__":
    main()
