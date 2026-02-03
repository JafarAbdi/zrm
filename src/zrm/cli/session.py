#!/usr/bin/env python3
"""CLI tool for inspecting ZRM sessions."""

import argparse
import sys

import zrm


class Style:
    """ANSI styles for terminal output."""

    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    R = "\033[0m"


def list_sessions():
    """List all sessions in the ZRM network."""
    with zrm.open(name="_zrm_cli") as session:
        graph = zrm.Graph(session)
        entities = graph.get_all_entities()

        # Group entities by session name, exclude our own CLI session.
        sessions: dict[str, list[zrm.Entity]] = {}
        for entity in entities:
            if entity.name == "_zrm_cli":
                continue
            sessions.setdefault(entity.name, []).append(entity)

        if not sessions:
            print(f"{Style.YELLOW}No sessions found in the network{Style.R}")
            graph.close()
            return

        for name in sorted(sessions):
            group = sessions[name]
            print(f"{Style.BOLD}{Style.GREEN}{name}{Style.R}")

            pubs = [e for e in group if e.kind == zrm.EntityKind.PUBLISHER]
            subs = [e for e in group if e.kind == zrm.EntityKind.SUBSCRIBER]
            servers = [e for e in group if e.kind == zrm.EntityKind.SERVER]
            clients = [e for e in group if e.kind == zrm.EntityKind.CLIENT]

            if pubs:
                print(f"  Publishers: {Style.BLUE}{len(pubs)}{Style.R}")
                for pub in pubs:
                    print(
                        f"    {Style.BLUE}{pub.topic}{Style.R}  {Style.DIM}{pub.type_name}{Style.R}"
                    )
            if subs:
                print(f"  Subscribers: {Style.BLUE}{len(subs)}{Style.R}")
                for sub in subs:
                    print(
                        f"    {Style.BLUE}{sub.topic}{Style.R}  {Style.DIM}{sub.type_name}{Style.R}"
                    )
            if servers:
                print(f"  Servers: {Style.BLUE}{len(servers)}{Style.R}")
                for srv in servers:
                    print(
                        f"    {Style.BLUE}{srv.topic}{Style.R}  {Style.DIM}{srv.type_name}{Style.R}"
                    )
            if clients:
                print(f"  Clients: {Style.BLUE}{len(clients)}{Style.R}")
                for client in clients:
                    print(
                        f"    {Style.BLUE}{client.topic}{Style.R}  {Style.DIM}{client.type_name}{Style.R}"
                    )

            print()

        graph.close()


def main():
    """Main entry point for zrm-session CLI."""
    parser = argparse.ArgumentParser(
        description="ZRM session inspection tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    subparsers.add_parser("list", help="List all sessions in the network")

    args = parser.parse_args()

    match args.command:
        case "list":
            list_sessions()
        case _:
            parser.print_help()
            sys.exit(1)


if __name__ == "__main__":
    main()
