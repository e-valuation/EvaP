import os.path
import sys
from subprocess import run

from django.core.management import call_command
from django.core.management.base import BaseCommand

from evap.evaluation.management.commands.tools import subprocess_run_or_exit


class Command(BaseCommand):
    help = "Run the visual regression testing suite"

    def handle(self, *args, **options):
        assert os.environ.get("VRT_APIURL"), "env var VRT_APIURL must be set"
        assert os.environ.get("VRT_APIKEY"), "env var VRT_APIKEY must be set"
        assert os.environ.get("VRT_PROJECT"), "env var VRT_PROJECT must be set"

        commit_hash = os.environ.get("VRT_CIBUILDID")
        if not commit_hash:
            commit_hash = run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, check=False)
            if commit_hash.returncode != 0:
                self.stderr.write(self.style.ERROR("Could not get commit hash: " + str(commit_hash.stderr)))
                sys.exit(1)
            commit_hash = commit_hash.stdout.decode().strip()
            self.stdout.write(self.style.NOTICE(f"using VRT_CIBUILDID = '{commit_hash}'"))
            os.environ["VRT_CIBUILDID"] = commit_hash

        branch_name = os.environ.get("VRT_BRANCHNAME")
        if not branch_name:
            branch_name = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, check=False)
            if branch_name.returncode != 0:
                self.stderr.write(self.style.ERROR("Could not get branch name: " + branch_name.stderr))
                sys.exit(1)
            branch_name = branch_name.stdout.decode().strip()
            self.stdout.write(self.style.NOTICE(f"using VRT_BRANCHNAME = '{branch_name}'"))
            os.environ["VRT_BRANCHNAME"] = branch_name

        call_command("ts", "compile")
        call_command("scss")

        # subprocess call so our sys.argv check in settings.py works
        subprocess_run_or_exit(["./manage.py", "test", "--tag", "vrt"], self.stdout)
