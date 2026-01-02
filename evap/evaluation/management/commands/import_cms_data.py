import argparse
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError

from evap.evaluation.management.commands.tools import log_exceptions
from evap.evaluation.models import Semester
from evap.staff.importers.json import JSONImporter

logger = logging.getLogger(__name__)

RETRIES = 3
TIMEOUT = 120


def parse_course_end_date(date_str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


@log_exceptions
class Command(BaseCommand):
    help = "Downloads the JSON file with the CMS data for a given semester and imports it."

    def add_arguments(self, parser: argparse.ArgumentParser):
        mode = parser.add_subparsers(help="import mode", required=True, dest="mode")

        download_mode = mode.add_parser("download")
        download_mode.add_argument("url", type=str)

        file_mode = mode.add_parser("file")
        file_mode.add_argument("path-to-json", type=Path)
        file_mode.add_argument("--semester-id", type=int, required=True)
        file_mode.add_argument("--default-course-end-date", type=parse_course_end_date)

    def handle(self, *args, **options):
        logger.info("import_cms_data called.")

        match options["mode"]:
            case "download":
                for semester in Semester.objects.filter(default_course_end_date__isnull=False, cms_name__ne=""):
                    logger.info("Downloading data for %s.", semester.name_en)
                    url = options["url"].format(urllib.parse.quote(semester.cms_name))
                    for _ in range(RETRIES):
                        try:
                            json_contents = requests.get(url, timeout=TIMEOUT).text
                            break
                        except requests.exceptions.Timeout:
                            logger.warning("Download timed out: %s", url)
                    else:
                        logger.warning("Giving up.")
                        continue

                    logger.info("Importing downloaded data for %s.", semester.name_en)
                    JSONImporter(semester, semester.default_course_end_date).import_json(json_contents)
                    logger.info("Finished %s.", semester.name_en)
            case "file":
                try:
                    semester = Semester.objects.get(id=options["semester_id"])
                except Semester.DoesNotExist as e:
                    raise CommandError("Semester does not exist.") from e

                logger.info("Loading file data for %s.", semester.name_en)
                default_course_end = options.get("default_course_end_date", semester.default_course_end_date)
                if not default_course_end:
                    raise CommandError("Semester has no default course end date, please specify one as an argument.")
                with open(options["path-to-json"], encoding="utf-8") as file:
                    JSONImporter(semester, default_course_end).import_json(file.read())
                logger.info("Finished %s.", semester.name_en)
