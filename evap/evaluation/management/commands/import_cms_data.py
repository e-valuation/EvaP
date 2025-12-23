import logging
import urllib.parse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import log_exceptions
from evap.evaluation.models import Semester
from evap.staff.importers.json import JSONImporter

logger = logging.getLogger(__name__)


@log_exceptions
class Command(BaseCommand):
    help = "Downloads the JSON file with the CMS data for a given semester and imports it."

    def handle(self, *args, **options):
        logger.info("import_cms_data called.")

        for semester in Semester.objects.filter(default_course_end_date__isnull=False).exclude(cms_name=""):
            logger.info("Processing %s.", semester.name_en)

            semester_string = urllib.parse.quote(semester.cms_name)
            url = settings.CMS_DATA_DOWNLOAD_URL.format(semester_string)
            filename = "CMS.json"
            download_successful = download(url, filename)
            if not download_successful:
                continue

            import_data(semester, filename)
            logger.info("Processing %s finished.", semester.name_en)

        logger.info("import_cms_data finished.")


def download(url, filename):
    logger.info("Downloading data.")
    tries = 0
    while tries < 3:
        try:
            response = requests.get(url, timeout=120)
            with open(filename, "wb") as file:
                for chunk in response.iter_content(chunk_size=128):
                    file.write(chunk)
            logger.info("CMS data downloaded.")
            return True
        except requests.exceptions.Timeout:
            tries += 1
            logger.warning("Download timeout.")
    logger.error("CMS data could not be downloaded.")
    return False


def import_data(semester, filename):
    logger.info("Importing CMS data.")
    with open(filename, encoding="utf-8") as file:
        JSONImporter(semester, semester.default_course_end_date).import_json(file.read())
