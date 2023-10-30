#!/usr/bin/env python3
import csv
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from io import BytesIO
from typing import TextIO

from openpyxl import load_workbook
from openpyxl.cell import Cell


@dataclass
class User:
    title: str
    last_name: str
    first_name: str
    email: str


@dataclass
class UserCells:
    title: Cell | None
    last_name: Cell
    first_name: Cell
    email: Cell

    def value(self) -> User:
        return User(
            str(self.title.value) if self.title and self.title.value else "",
            str(self.last_name.value),
            str(self.first_name.value),
            str(self.email.value),
        )


def user_decision(field: str, existing: str, imported: str) -> str:
    if existing == imported:
        return existing
    decision = input(f"Do you want to keep the existing user {field}? (Y/n) ")
    if decision and decision[0].lower() == "n":
        return imported
    return existing


def fix_user(users: dict[str, User], imported_cells: UserCells) -> None:
    imported = imported_cells.value()
    existing = users.setdefault(imported.email, imported)
    if imported == existing:
        return
    print("There is a conflict in the user data.")
    print(f"existing: {existing}.")
    print(f"imported: {imported}.")
    # None is passed exclusively for participants since they have no title column
    if imported_cells.title is not None:
        imported_cells.title.value = user_decision("title", existing.title, imported.title)
    imported_cells.last_name.value = user_decision("last name", existing.last_name, imported.last_name)
    imported_cells.first_name.value = user_decision("first name", existing.first_name, imported.first_name)
    imported_cells.email.value = user_decision("email", existing.email, imported.email)
    print()


def run_preprocessor(enrollment_data: str | BytesIO, user_data: TextIO) -> BytesIO:
    workbook = load_workbook(enrollment_data)
    users = {}
    reader = csv.reader(user_data, delimiter=";", lineterminator="\n")
    for row in reader:
        email = row[-1]
        users[email] = User(*row)
    for sheet in workbook.worksheets:
        for wb_row in sheet.iter_rows(min_row=2, min_col=2):
            fix_user(users, UserCells(None, *wb_row[:3]))
            fix_user(users, UserCells(*wb_row[7:]))
    wb_out = BytesIO()
    workbook.save(wb_out)
    return wb_out


if __name__ == "__main__":  # pragma: nocover
    parser = ArgumentParser(description="Commandline tool to preprocess enrollment xlsx files.")
    parser.add_argument(
        "user-data", help="Path to a csv file containing an export of all existing users."
    )
    parser.add_argument(
        "enrollment-data", help="Path to the enrollment data in xlsx format for import."
    )
    ns = parser.parse_args(sys.argv)
    with open(ns.user_data, encoding="utf-8") as csvfile:
        wb = run_preprocessor(ns.enrollment_data, csvfile)
    with open(ns.enrollment_data, "wb", encoding="utf-8") as out:
        out.write(wb.read())
