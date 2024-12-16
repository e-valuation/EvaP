#!/usr/bin/env bash

# Counter part for update_production script.
# This script will import the backup made by update_production.

set -e # abort on error
cd "$(dirname "$0")/.." # change to root directory

CONDITIONAL_NOINPUT=""
[[ ! -z "$GITHUB_WORKFLOW" ]] && echo "Detected GitHub" && CONDITIONAL_NOINPUT="--noinput" && EVAP_SKIP_APACHE_STEPS=1

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

[[ -z "$EVAP_SKIP_APACHE_STEPS" ]] && sudo service apache2 stop

# sometimes, this fails for some random i18n test translation files.
python -m evap compilemessages || true
python -m evap scss --production
python -m evap collectstatic --noinput

python -m evap reset_db "$CONDITIONAL_NOINPUT"
python -m evap migrate
python -m evap flush "$CONDITIONAL_NOINPUT"
python -m evap loaddata_unlogged "$1"

python -m evap clear_cache --all -v=1
python -m evap refresh_results_cache

[[ -z "$EVAP_SKIP_APACHE_STEPS" ]] && sudo service apache2 start

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo "Backup restored."
