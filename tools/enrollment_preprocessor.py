#!/usr/bin/env python3

import csv
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterator, NamedTuple, TextIO

from openpyxl import Workbook, load_workbook
from openpyxl.cell import Cell


@dataclass
class User:
    title: str
    last_name: str
    first_name: str
    email: str

    def full_name(self) -> str:
        prefix = ""
        if self.title:
            prefix = f"{self.title} "
        return f"{prefix}{self.first_name} {self.last_name}, {self.email}"


class UserCells(NamedTuple):
    title: Cell | None
    last_name: Cell
    first_name: Cell
    email: Cell

    def clean(self) -> Iterator[str]:
        for field in iter(self):
            if not field or not field.value:
                yield ""
                continue
            field.value = str(field.value or "").strip()
            yield field.value


def make_bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def group_conflicts(
    users: dict[str, User], user_cells: dict[tuple[str, ...], UserCells]
) -> dict[str, list[tuple[UserCells, User]]]:
    groups = defaultdict(list)
    for cells in user_cells.values():
        imported = User(*cells.clean())
        existing = users.setdefault(imported.email, imported)
        if not imported.email or imported == existing:
            continue

        for field in ["title", "last_name", "first_name"]:
            field_value = getattr(cells, field)
            if field_value is not None and getattr(existing, field) != getattr(imported, field):
                groups[field].append((cells, existing))
    return groups


def parse_existing(user_data: TextIO) -> dict[str, User]:
    users = {}
    reader = csv.reader(user_data, delimiter=";", lineterminator="\n")
    next(reader)  # skip header
    for row in reader:
        user = User(*row)
        users[user.email] = user
    return users


def parse_imported(enrollment_data: Workbook):
    user_cells: dict[tuple[str, ...], UserCells] = {}
    for sheet in enrollment_data.worksheets:
        for wb_row in sheet.iter_rows(min_row=2, min_col=2):
            cells = UserCells(None, *wb_row[:3])
            user_cells.setdefault(tuple(cells.clean()), cells)
            cells = UserCells(*wb_row[7:])
            user_cells.setdefault(tuple(cells.clean()), cells)
    return user_cells


def run_preprocessor(enrollment_data: Path | BytesIO, user_data: TextIO) -> BytesIO | None:
    workbook = load_workbook(enrollment_data)

    conflict_groups = group_conflicts(parse_existing(user_data), parse_imported(workbook))

    changed = False
    for field, conflicts in conflict_groups.items():
        print(field.capitalize())
        print("---------")
        for cells, existing in conflicts:
            imported = User(*cells.clean())
            print(f"existing: '{make_bold(getattr(existing, field))}' ({existing.full_name()})")
            print(f"imported: '{make_bold(getattr(imported, field))}' ({imported.full_name()})")

            decision: str = ""
            while decision not in ("e", "i"):
                decision = input("Which one should be used? (e/i):\n")
            if decision == "e":
                getattr(cells, field).value = getattr(existing, field)
                changed = True
        print()

    if not changed:
        return None
    wb_out = BytesIO()
    workbook.save(wb_out)
    wb_out.seek(0)
    return wb_out


if __name__ == "__main__":  # pragma: nocover
    parser = ArgumentParser(description="Commandline tool to preprocess enrollment xlsx files.")
    parser.add_argument("user_data", help="Path to a csv file containing an export of all existing users.")
    parser.add_argument("enrollment_data", help="Path to the enrollment data in xlsx format for import.")
    ns = parser.parse_args()

    target = Path(ns.enrollment_data)

    with open(ns.user_data, encoding="utf-8") as csvfile:
        wb = run_preprocessor(target, csvfile)
        if wb is None:
            sys.exit()
    with open(target.with_stem(f"{target.stem}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"), "wb") as out:
        out.write(wb.read())
