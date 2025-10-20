#!/usr/bin/env python3

import argparse
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile

from pathspec.patterns.gitwildmatch import GitWildMatchPattern


def ensure_all_artifacts_included(pyproject, wheel_paths):
    try:
        artifacts = pyproject["tool"]["hatch"]["build"]["artifacts"]
    except KeyError:
        print("No artifacts specified")
        return 0
    status = 0
    for wheel_path in wheel_paths:
        with ZipFile(wheel_path) as f:
            included_files = f.namelist()
        for artifact in artifacts:
            pattern = GitWildMatchPattern(artifact)
            if all(pattern.match_file(name) is None for name in included_files):
                print(f"{wheel_path}: No file matches artifact: {artifact}", file=sys.stderr)
                status |= 1
    return status


def main(argv):
    parser = argparse.ArgumentParser("check_dist", exit_on_error=False)
    parser.add_argument("pyproject", type=Path)
    parser.add_argument("wheels", type=Path, nargs="*")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    with args.pyproject.open("rb") as f:
        pyproject = tomllib.load(f)

    return ensure_all_artifacts_included(pyproject, args.wheels)


if __name__ == "__main__":  # pragma: nocover
    sys.exit(main(sys.argv[1:]))
