#!/usr/bin/env python3
import csv
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from io import BytesIO
from typing import Iterator, TextIO

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

    def value(self):
        return User(
            self.title.value or "" if self.title else "", self.last_name.value, self.first_name.value, self.email.value
        )


def user_decision(field: str, existing: str, imported: str) -> str:
    if existing == imported:
        return existing
    decision = input(f"Do you want to keep the existing user {field}? (y/n) ")
    if decision and decision[0].lower() == "n":
        return imported
    return existing


def fix_users(users: dict[str, User], imported_cells: UserCells):
    imported = imported_cells.value()
    existing = users.setdefault(imported.email, imported)
    if imported == existing:
        return
    print("There is a conflict in the user data.")
    print(f"existing: {existing}.")
    print(f"imported: {imported}.")
    if imported_cells.title is not None:
        imported_cells.title.value = user_decision("title", existing.title, imported.title)
    imported_cells.last_name.value = user_decision("last name", existing.last_name, imported.last_name)
    imported_cells.first_name.value = user_decision("first name", existing.first_name, imported.first_name)
    imported_cells.email.value = user_decision("email", existing.email, imported.email)
    print()


def run_preprocessor(enrollment_data: str | BytesIO, user_data: TextIO):
    workbook = load_workbook(enrollment_data)
    users = {}
    reader = csv.reader(user_data, delimiter=";", lineterminator="\n")
    for row in reader:
        users[row[-1]] = User(*row)
    for sheet_name in ["MA Belegungen", "BA Belegungen"]:
        for wb_row in workbook[sheet_name].iter_rows(min_row=2, min_col=2):
            fix_users(users, UserCells(None, *wb_row[:3]))
            fix_users(users, UserCells(*wb_row[7:]))
    workbook.save(enrollment_data)


if __name__ == "__main__":
    parser = ArgumentParser(description="Commandline tool to preprocess enrollment xlsx files.")
    parser.add_argument(
        "-u", "--user-data", help="Path to a csv file containing an export of all existing users.", required=True
    )
    parser.add_argument(
        "-e", "--enrollment-data", help="Path to the enrollment data in xlsx format for import.", required=True
    )
    ns = parser.parse_args(sys.argv[1:])
    with open(ns.user_data, encoding="utf-8") as csvfile:
        run_preprocessor(ns.enrollment_data, csvfile)
