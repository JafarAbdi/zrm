#!/usr/bin/env python3
"""CLI tool for inspecting ZRM sessions."""

import argparse
import sys

import zrm
from zrm import cli


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
            print(f"{cli.Style.YELLOW}No sessions found in the network{cli.Style.R}")
            graph.close()
            return

        for name in sorted(sessions):
            group = sessions[name]
            print(f"{cli.Style.BOLD}{cli.Style.GREEN}{name}{cli.Style.R}")

            pubs = [e for e in group if e.kind == zrm.EntityKind.PUBLISHER]
            subs = [e for e in group if e.kind == zrm.EntityKind.SUBSCRIBER]
            servers = [e for e in group if e.kind == zrm.EntityKind.SERVER]
            clients = [e for e in group if e.kind == zrm.EntityKind.CLIENT]

            if pubs:
                print(f"  Publishers: {cli.Style.BLUE}{len(pubs)}{cli.Style.R}")
                for pub in pubs:
                    print(
                        f"    {cli.Style.BLUE}{pub.topic}{cli.Style.R}  {cli.Style.DIM}{pub.type_name}{cli.Style.R}"
                    )
            if subs:
                print(f"  Subscribers: {cli.Style.BLUE}{len(subs)}{cli.Style.R}")
                for sub in subs:
                    print(
                        f"    {cli.Style.BLUE}{sub.topic}{cli.Style.R}  {cli.Style.DIM}{sub.type_name}{cli.Style.R}"
                    )
            if servers:
                print(f"  Servers: {cli.Style.BLUE}{len(servers)}{cli.Style.R}")
                for srv in servers:
                    print(
                        f"    {cli.Style.BLUE}{srv.topic}{cli.Style.R}  {cli.Style.DIM}{srv.type_name}{cli.Style.R}"
                    )
            if clients:
                print(f"  Clients: {cli.Style.BLUE}{len(clients)}{cli.Style.R}")
                for client in clients:
                    print(
                        f"    {cli.Style.BLUE}{client.topic}{cli.Style.R}  {cli.Style.DIM}{client.type_name}{cli.Style.R}"
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
