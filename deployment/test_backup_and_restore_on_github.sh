#! /usr/bin/env bash

# This assumes we are running on GitHub and the database exists, but is empty.
# create a backup and load it again
python manage.py migrate
python manage.py loaddata test_data
EVAP_OVERRIDE_BACKUP_FILENAME=true EVAP_SKIP_CHECKOUT=true EVAP_RUNNING_INSIDE_GITHUB=true deployment/update_production.sh backup.json
echo "yy" | EVAP_RUNNING_INSIDE_GITHUB=true deployment/load_production_backup.sh backup.json
