#!/usr/bin/env python3
import csv
import sys
from argparse import ArgumentParser
from dataclasses import dataclass

from openpyxl import load_workbook
from openpyxl.cell import Cell


@dataclass
class User:
    title: str
    last_name: str
    first_name: str
    email: str


def fix_users(users: dict[str, User], title: Cell | None, last_name: Cell, first_name: Cell, email: Cell):
    imported = User(last_name=last_name.value, first_name=first_name.value, email=email.value, title=title.value or "" if title else "")  # type: ignore[arg-type]  # if schema is correct, all values are strings
    existing = users.setdefault(imported.email, imported)
    if existing != imported:
        print("There is a conflict in the user data.")
        print(f"existing: {existing}.")
        print(f"imported: {imported}.")
        if input("Do you want to keep the existing user? (y/n)")[0].lower() == "n":
            return

        email.value = existing.email
        last_name.value = existing.last_name
        first_name.value = existing.first_name
        if title:
            title.value = existing.title


if __name__ == "__main__":
    args = sys.argv
    if "python" in args[0]:
        args = args[1:]
    parser = ArgumentParser(description="Commandline tool to preprocess enrollment xlsx files.")
    parser.add_argument(
        "-ud", "--user-data", help="Path to a csv file containing an export of all existing users.", required=True
    )
    parser.add_argument(
        "-ed", "--enrollment-data", help="Path to the enrollment data in xlsx format for import.", required=True
    )
    ns = parser.parse_args(sys.argv[1:])

    workbook = load_workbook(ns.enrollment_data)
    user_dict = {}
    with open(ns.user_data, encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            print(*row)
            user_dict[row[0]] = User(*row)
    for sheet_name in ["MA Belegungen", "BA Belegungen"]:
        for row in workbook[sheet_name].iter_rows(min_row=2, min_col=2):
            fix_users(user_dict, None, *row[:3])
            fix_users(user_dict, *row[7:])
    workbook.save(ns.enrollment_data)
