#!/usr/bin/env python3

import sys
import tomllib
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
                print(f"{wheel_path}: No file matches artifact: {artifact}")
                status |= 1
    return status


def main():
    if len(sys.argv) < 3:
        print(f"USAGE: {sys.argv[0]} <pyproject.toml path> <.whl path>...")
        return 1

    with open(sys.argv[1], "rb") as f:
        pyproject = tomllib.load(f)

    return ensure_all_artifacts_included(pyproject, sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
