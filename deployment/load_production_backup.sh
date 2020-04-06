#!/bin/bash

# Counter part for update_production script.
# This script will import the backup made by update_production.

set -e # abort on error
cd $(dirname $0)/.. # change to root directory

USERNAME="evap"
ENVDIR="/opt/evap/env"
ADDITIONAL_ARGUMENTS=""
[[ ! -z "$EVAP_RUNNING_INSIDE_TRAVIS" ]] && echo "Detected travis" && USERNAME="travis" && ENVDIR=~/virtualenv/python3.7 && ADDITIONAL_ARGUMENTS=" --noinput"

COMMIT_HASH="$(git rev-parse --short HEAD)"

# argument 1 is the filename for the backupfile.
if [ ! $# -eq 1 ] # if there is exactly one argument
    then
        echo "Please specify a backup file to import as command line argument."
        exit
fi

# Check if commit hash is in file name. Ask for confirmation if its not there.
if [[ ! $1 =~ ${COMMIT_HASH} ]]
then
    echo "Looks like the backup was made on another commit. Currently, you are on ${COMMIT_HASH}."
    read -p "Do you want to continue [y]? " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]
    then
        exit 1
    fi
fi

echo "WARNING! This will cause IRREPARABLE DATA LOSS."
read -p "Are you sure you want to continue [y]? " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    exit 1
fi

[[ -z "$EVAP_RUNNING_INSIDE_TRAVIS" ]] && sudo service apache2 stop

sudo -H -u $USERNAME $ENVDIR/bin/pip install -r requirements.txt

# compilemessages and compress regularly fail without any real issue.
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py compilemessages || true
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py collectstatic --noinput
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py compress --verbosity=0 || true

sudo -H -u $USERNAME $ENVDIR/bin/python manage.py reset_db $ADDITIONAL_ARGUMENTS
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py migrate
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py flush $ADDITIONAL_ARGUMENTS
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py loaddata $1

sudo -H -u $USERNAME $ENVDIR/bin/python manage.py clear_cache
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py refresh_results_cache

sudo -H -u $USERNAME $ENVDIR/bin/python manage.py clear_cache --cache=sessions

[[ -z "$EVAP_RUNNING_INSIDE_TRAVIS" ]] && sudo service apache2 start

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo "Backup restored."
