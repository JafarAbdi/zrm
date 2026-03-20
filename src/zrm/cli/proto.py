#!/usr/bin/env python3
"""CLI tool for generating Python modules from protobuf definitions."""

import argparse
import importlib.resources
import pathlib
import subprocess
import sys

from zrm import cli


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
        print(f"{cli.Style.RED}Error:{cli.Style.R} {result.stderr}", file=sys.stderr)
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


def collect_proto_files(
    package: str | None,
    proto_dir: pathlib.Path | None,
    deps: list[str],
    categories: list[str],
) -> dict[str, list[pathlib.Path]]:
    """Collect proto files for a package and its dependencies.

    Returns a mapping of package name to list of proto file paths.
    Raises LookupError if a dependency's proto directory cannot be found.
    """
    packages: list[tuple[str, pathlib.Path]] = []
    if package and proto_dir:
        packages.append((package, proto_dir))

    for dep in deps:
        dep_proto_dir = get_package_proto_dir(dep)
        if dep_proto_dir is None:
            raise LookupError(f"Could not find proto dir for package '{dep}'")
        packages.append((dep, dep_proto_dir))

    result: dict[str, list[pathlib.Path]] = {}
    for name, path in packages:
        files: list[pathlib.Path] = []
        for category in categories:
            files.extend(find_proto_files(path / category))
        result[name] = files
    return result


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
    parser.add_argument(
        "--list",
        action="store_true",
        help="List proto file paths for the current package and dependencies.",
    )

    args = parser.parse_args()

    categories = ["msgs", "srvs", "actions"]

    # Find package from current directory (optional for --list)
    result = find_package()

    if args.list:
        package, proto_dir = result if result else (None, None)
        collected = collect_proto_files(package, proto_dir, args.dep, categories)
        if not collected:
            print(
                "No proto files found. Use --dep PKG to list protos from an installed package."
            )
            return
        for name, files in collected.items():
            print(f"{cli.Style.CYAN}{name}{cli.Style.R}")
            for proto_file in files:
                print(f"  {proto_file}")
        return

    if result is None:
        print(
            f"{cli.Style.RED}Error:{cli.Style.R} No package with proto/ directory found in src/",
            file=sys.stderr,
        )
        sys.exit(1)

    package, proto_dir = result

    out_dir = args.out_dir.resolve()

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
                f"{cli.Style.RED}Error:{cli.Style.R} Could not find proto dir for package '{dep}'",
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

    print(f"{cli.Style.CYAN}Package:{cli.Style.R} {package}")
    print(f"{cli.Style.CYAN}Proto dir:{cli.Style.R} {proto_dir}")
    print(f"{cli.Style.CYAN}Output dir:{cli.Style.R} {out_dir}")
    print(f"{cli.Style.CYAN}Proto paths:{cli.Style.R}")
    for mapping, path in proto_paths:
        print(f"  {cli.Style.DIM}{mapping}{cli.Style.R} -> {path}")
    print(f"{cli.Style.CYAN}Files:{cli.Style.R} {[f.name for f in proto_files]}")
    print()

    if generate(proto_files, out_dir, proto_paths):
        print(
            f"{cli.Style.GREEN}Generated {len(proto_files)} proto file(s){cli.Style.R}"
        )
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
