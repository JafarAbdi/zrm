#!/usr/bin/env python3
"""CLI tool for inspecting ZRM topics."""

import argparse
import sys
import time

from google.protobuf import text_format

import zrm
from zrm import cli


def list_topics():
    """List all topics in the ZRM network."""
    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        topics = graph.get_topics()

        if not topics:
            print(f"{cli.Style.YELLOW}No topics found in the network{cli.Style.R}")
            graph.close()
            return

        for topic_name, type_name in sorted(topics):
            print(f"{cli.Style.BOLD}{cli.Style.GREEN}{topic_name}{cli.Style.R}")
            print(f"  Type: {cli.Style.DIM}{type_name}{cli.Style.R}")

            publishers = graph.get_publishers(topic_name)
            if publishers:
                names = [e.name for e in publishers]
                print(
                    f"  Publishers: {cli.Style.CYAN}{len(names)}{cli.Style.R} {cli.Style.DIM}{names}{cli.Style.R}"
                )

            subscribers = graph.get_subscribers(topic_name)
            if subscribers:
                names = [e.name for e in subscribers]
                print(
                    f"  Subscribers: {cli.Style.BLUE}{len(names)}{cli.Style.R} {cli.Style.DIM}{names}{cli.Style.R}"
                )

            print()

        graph.close()


def pub_topic(topic: str, msg_type_name: str | None, data: str, rate: float):
    """Publish messages to a topic."""
    cli.validate_name(topic)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        msg_type_name = cli.resolve_topic_type(graph, topic, msg_type_name)
        msg_type = cli.load_message_type(msg_type_name)

        msg = msg_type()
        try:
            text_format.Parse(data, msg)
        except text_format.ParseError as e:
            print(f"{cli.Style.RED}Error parsing message data: {e}{cli.Style.R}")
            graph.close()
            sys.exit(1)

        pub = zrm.Publisher(session, topic, msg_type)

        print(f"Publishing to {cli.Style.BOLD}{topic}{cli.Style.R} at {rate} Hz")

        try:
            interval = 1.0 / rate
            while True:
                pub.publish(msg)
                print(
                    f"{cli.Style.DIM}{text_format.MessageToString(msg, as_one_line=True)}{cli.Style.R}"
                )
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            pub.close()
            graph.close()


def echo_topic(topic: str, msg_type_name: str | None):
    """Echo messages from a topic."""
    cli.validate_name(topic)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        msg_type_name = cli.resolve_topic_type(graph, topic, msg_type_name)
        msg_type = cli.load_message_type(msg_type_name)

        publishers = graph.get_publishers(topic)
        if publishers:
            names = ", ".join(e.name for e in publishers)
            print(f"{cli.Style.DIM}Publishers: {names}{cli.Style.R}")

        def callback(msg):
            print(f"{cli.Style.BOLD}{topic}{cli.Style.R}")
            print(
                f"{cli.Style.DIM}{text_format.MessageToString(msg)}{cli.Style.R}",
                end="",
            )

        sub = zrm.Subscriber(session, topic, msg_type, callback=callback)

        print(f"Listening to {cli.Style.BOLD}{topic}{cli.Style.R}\n")

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
    cli.validate_name(topic)

    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        msg_type_name = cli.resolve_topic_type(graph, topic, msg_type_name)
        msg_type = cli.load_message_type(msg_type_name)

        publishers = graph.get_publishers(topic)
        if publishers:
            names = ", ".join(e.name for e in publishers)
            print(f"{cli.Style.DIM}Publishers: {names}{cli.Style.R}")

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
                    f"  {cli.Style.BOLD}{hz:.2f} Hz{cli.Style.R}  {cli.Style.DIM}(avg of {msg_count}){cli.Style.R}"
                )

        sub = zrm.Subscriber(session, topic, msg_type, callback=callback)

        print(f"Measuring {cli.Style.BOLD}{topic}{cli.Style.R}\n")

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
    except (ValueError, LookupError) as e:
        print(f"{cli.Style.RED}Error: {e}{cli.Style.R}")
        sys.exit(1)


if __name__ == "__main__":
    main()
