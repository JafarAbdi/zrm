#!/usr/bin/env python3
"""CLI tool for generating Python modules from protobuf definitions."""

import argparse
import importlib.resources
import pathlib
import subprocess
import sys


class Color:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"
    DIM = "\033[2m"


def get_package_proto_dir(package: str) -> pathlib.Path | None:
    """Get proto directory for an installed package."""
    try:
        pkg_files = importlib.resources.files(package)
        proto_dir = pkg_files.joinpath("proto")
        # Convert to real path
        with importlib.resources.as_file(proto_dir) as path:
            if path.is_dir():
                return path
    except (ModuleNotFoundError, TypeError, FileNotFoundError):
        pass
    return None


def find_proto_files(directory: pathlib.Path) -> list[pathlib.Path]:
    """Find all .proto files in a directory (non-recursive)."""
    if not directory.is_dir():
        return []
    return list(directory.glob("*.proto"))


def generate(
    proto_files: list[pathlib.Path],
    out_dir: pathlib.Path,
    proto_paths: list[tuple[str, pathlib.Path]],
) -> bool:
    """Generate Python and stub files from .proto files."""
    if not proto_files:
        return True

    cmd = [
        "protoc",
        f"--python_out={out_dir}",
        f"--pyi_out={out_dir}",
    ]
    for mapping, path in proto_paths:
        cmd.append(f"--proto_path={mapping}={path}")
    cmd.extend(str(f) for f in proto_files)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"{Color.RED}Error:{Color.RESET} {result.stderr}", file=sys.stderr)
        return False
    return True


def find_package() -> tuple[str, pathlib.Path] | None:
    """Find package name and proto dir from current directory structure."""
    src_dir = pathlib.Path("src").resolve()
    if not src_dir.is_dir():
        return None

    for pkg_dir in src_dir.iterdir():
        if not pkg_dir.is_dir():
            continue
        proto_dir = pkg_dir / "proto"
        if proto_dir.is_dir():
            return pkg_dir.name, proto_dir

    return None


def main():
    """Main entry point for zrm-proto CLI."""
    parser = argparse.ArgumentParser(
        description="Generate Python modules from protobuf definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate protos (run from package root)
  zrm-proto

  # Generate protos for a package that depends on zrm
  zrm-proto --dep zrm
""",
    )
    parser.add_argument(
        "--dep",
        action="append",
        default=[],
        metavar="PKG",
        help="Dependency package name (e.g., zrm). Can be specified multiple times.",
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=pathlib.Path("src"),
        help="Output directory (default: src)",
    )

    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    categories = ["msgs", "srvs"]

    # Find package from current directory
    result = find_package()
    if result is None:
        print(
            f"{Color.RED}Error:{Color.RESET} No package with proto/ directory found in src/",
            file=sys.stderr,
        )
        sys.exit(1)

    package, proto_dir = result

    # Build proto paths for this package
    proto_paths: list[tuple[str, pathlib.Path]] = []
    for category in categories:
        category_dir = proto_dir / category
        if category_dir.is_dir():
            proto_paths.append((f"{package}/{category}", category_dir))

    # Add dependency proto paths (from installed packages)
    for dep in args.dep:
        dep_proto_dir = get_package_proto_dir(dep)
        if dep_proto_dir is None:
            print(
                f"{Color.RED}Error:{Color.RESET} Could not find proto dir for package '{dep}'",
                file=sys.stderr,
            )
            sys.exit(1)

        for category in categories:
            category_dir = dep_proto_dir / category
            if category_dir.is_dir():
                proto_paths.append((f"{dep}/{category}", category_dir))

    if not proto_paths:
        print(f"No proto directories found in {proto_dir}")
        sys.exit(1)

    # Collect proto files from this package only (not dependencies)
    proto_files: list[pathlib.Path] = []
    for category in categories:
        proto_files.extend(find_proto_files(proto_dir / category))

    if not proto_files:
        print("No .proto files found")
        sys.exit(0)

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"{Color.CYAN}Package:{Color.RESET} {package}")
    print(f"{Color.CYAN}Proto dir:{Color.RESET} {proto_dir}")
    print(f"{Color.CYAN}Output dir:{Color.RESET} {out_dir}")
    print(f"{Color.CYAN}Proto paths:{Color.RESET}")
    for mapping, path in proto_paths:
        print(f"  {Color.DIM}{mapping}{Color.RESET} -> {path}")
    print(f"{Color.CYAN}Files:{Color.RESET} {[f.name for f in proto_files]}")
    print()

    if generate(proto_files, out_dir, proto_paths):
        print(f"{Color.GREEN}Generated {len(proto_files)} proto file(s){Color.RESET}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
