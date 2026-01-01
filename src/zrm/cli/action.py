#!/usr/bin/env python3
"""CLI tool for inspecting and interacting with ZRM actions."""

import argparse
import sys

from google.protobuf import text_format

import zrm


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


def list_actions():
    """List all actions in the ZRM network."""
    node = zrm.Node("_zrm_cli_action")

    actions = node.graph.get_action_names_and_types()

    if not actions:
        print(f"{Color.YELLOW}No actions found in the network{Color.RESET}")
        node.close()
        return

    print(f"{Color.BOLD}{Color.CYAN}=== ZRM Actions ==={Color.RESET}\n")

    for action_name, type_name in sorted(actions):
        print(f"{Color.BOLD}{Color.GREEN}{action_name}{Color.RESET}")
        print(f"  Type: {Color.DIM}{type_name}{Color.RESET}")

        # Get action servers for this action
        servers = node.graph.get_entities_by_action(
            zrm.EntityKind.ACTION_SERVER, action_name
        )
        if servers:
            server_nodes = [e.node_name for e in servers]
            server_count = len(server_nodes)
            print(
                f"  Servers: {Color.GREEN}{server_count}{Color.RESET} {Color.DIM}{server_nodes}{Color.RESET}"
            )

        # Get action clients for this action
        clients = node.graph.get_entities_by_action(
            zrm.EntityKind.ACTION_CLIENT, action_name
        )
        if clients:
            client_nodes = [e.node_name for e in clients]
            client_count = len(client_nodes)
            print(
                f"  Clients: {Color.YELLOW}{client_count}{Color.RESET} {Color.DIM}{client_nodes}{Color.RESET}"
            )

        print()

    node.close()


def send_goal(action: str, action_type_name: str | None, data: str, no_wait: bool):
    """Send a goal to an action server.

    Args:
        action: Action name
        action_type_name: Protobuf action type name (auto-discovered if None)
        data: Goal data in protobuf text format
        no_wait: If True, don't wait for result
    """
    node = zrm.Node("_zrm_cli_send")

    # Auto-discover type if not provided
    if action_type_name is None:
        try:
            actions = node.graph.get_action_names_and_types()
            for act_name, type_name in actions:
                if act_name == action:
                    action_type_name = type_name
                    print(
                        f"{Color.DIM}Auto-discovered type: {action_type_name}{Color.RESET}"
                    )
                    break
            else:
                raise ValueError(f"Action '{action}' not found in the network")
        except ValueError as e:
            print(f"{Color.RED}Error: {e}{Color.RESET}")
            print(
                f"{Color.YELLOW}Hint: Action not found. You must specify the type with --type{Color.RESET}"
            )
            node.close()
            sys.exit(1)

    try:
        action_type = zrm.get_message_type(action_type_name)
    except (ImportError, AttributeError, ValueError) as e:
        print(f"{Color.RED}Error loading action type: {e}{Color.RESET}")
        print(f"{Color.YELLOW}Type specified: {action_type_name}{Color.RESET}")
        print(
            f"{Color.YELLOW}Hint: Type format should be 'package/category/module/Type' (e.g., 'zrm/actions/examples/Fibonacci'){Color.RESET}"
        )
        node.close()
        sys.exit(1)

    # Parse the goal from text format
    goal = action_type.Goal()
    try:
        text_format.Parse(data, goal)
    except text_format.ParseError as e:
        print(f"{Color.RED}Error parsing goal data: {e}{Color.RESET}")
        node.close()
        sys.exit(1)

    # Create client
    client = node.create_action_client(action, action_type)

    print(
        f"{Color.GREEN}Sending goal to {Color.BOLD}{action}{Color.RESET}{Color.GREEN} [{action_type_name}]{Color.RESET}"
    )
    print(
        f"{Color.DIM}Goal: {text_format.MessageToString(goal, as_one_line=True)}{Color.RESET}\n"
    )

    def feedback_callback(feedback):
        print(f"{Color.CYAN}Feedback:{Color.RESET}")
        print(f"{Color.DIM}{text_format.MessageToString(feedback)}{Color.RESET}")

    try:
        goal_handle = client.send_goal(goal, feedback_callback=feedback_callback)
        print(
            f"{Color.GREEN}Goal accepted with ID: {goal_handle.goal_id}{Color.RESET}\n"
        )

        if no_wait:
            print(
                f"{Color.YELLOW}Not waiting for result (--no-wait specified){Color.RESET}"
            )
        else:
            print(f"{Color.DIM}Waiting for result... (Ctrl+C to cancel){Color.RESET}\n")
            try:
                result = goal_handle.get_result(timeout=300.0)
                print(f"{Color.GREEN}Result ({goal_handle.status}):{Color.RESET}")
                print(f"{Color.DIM}{text_format.MessageToString(result)}{Color.RESET}")
            except KeyboardInterrupt:
                print(f"\n{Color.YELLOW}Canceling goal...{Color.RESET}")
                if goal_handle.cancel():
                    print(f"{Color.GREEN}Cancel request sent{Color.RESET}")
                    # Wait briefly for cancellation to complete
                    goal_handle.wait_for_result(timeout=5.0)
                    print(
                        f"{Color.YELLOW}Final status: {goal_handle.status}{Color.RESET}"
                    )
                else:
                    print(f"{Color.RED}Failed to cancel goal{Color.RESET}")
            except TimeoutError:
                print(f"{Color.RED}Timeout waiting for result{Color.RESET}")
            except zrm.ActionError as e:
                print(f"{Color.RED}Action error: {e}{Color.RESET}")

    except zrm.ActionError as e:
        print(f"{Color.RED}Error: {e}{Color.RESET}")
        sys.exit(1)
    except TimeoutError as e:
        print(f"{Color.RED}Timeout: {e}{Color.RESET}")
        sys.exit(1)
    finally:
        client.close()
        node.close()


def main():
    """Main entry point for zrm-action CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM action inspection and interaction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all actions
  zrm-action list

  # Send a goal (auto-discover type)
  zrm-action send fibonacci 'order: 10'

  # Send a goal with explicit type
  zrm-action send fibonacci 'order: 10' -t zrm/actions/examples/Fibonacci

  # Send a goal without waiting for result
  zrm-action send fibonacci 'order: 10' --no-wait
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    subparsers.add_parser("list", help="List all actions in the network")

    # Send command
    send_parser = subparsers.add_parser("send", help="Send a goal to an action server")
    send_parser.add_argument("action", help="Action name")
    send_parser.add_argument("data", help="Goal data in protobuf text format")
    send_parser.add_argument(
        "-t",
        "--type",
        dest="action_type",
        help="Action type (e.g., zrm/actions/examples/Fibonacci). Auto-discovered if not specified.",
    )
    send_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for result after sending goal",
    )

    args = parser.parse_args()

    match args.command:
        case "list":
            list_actions()
        case "send":
            send_goal(args.action, args.action_type, args.data, args.no_wait)
        case _:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
