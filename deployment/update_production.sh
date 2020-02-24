#!/bin/bash
set -e # abort on error
cd $(dirname $0)/.. # change to project root directory

echo $PWD

# used for constructing the backup file name
COMMIT_HASH="$(git rev-parse --short HEAD)"
BACKUP_TITLE="backup"
TIMESTAMP="$(date +%Y-%m-%d_%H:%M:%S)"

USERNAME="evap"
ENVDIR="/opt/evap/env"
[[ ! -z "$EVAP_RUNNING_INSIDE_TRAVIS" ]] && echo "Detected travis" && USERNAME="travis" && ENVDIR=~/virtualenv/python3.7

# argument 1 is the title for the backupfile.
if [ $# -eq 1 ]
    then
        BACKUP_TITLE=$1
fi

FILENAME="${TIMESTAMP}_${COMMIT_HASH}_${BACKUP_TITLE}.json"

[[ -z "$EVAP_OVERRIDE_BACKUP_FILENAME" ]] && echo "Overriding Automatic Filename"
[[ -z "$EVAP_OVERRIDE_BACKUP_FILENAME" ]] || FILENAME="${BACKUP_TITLE}"

echo "Backup will be stored in $FILENAME"
echo "Starting update..."

set -x # print executed commands. enable this here to not print the if above.

sudo -H -u $USERNAME git fetch

# Note that apache should not be running during most of the upgrade,
# since then e.g. the backup might be incomplete or the code does not
# match the database layout, or https://github.com/e-valuation/EvaP/issues/1237.
[[ -z "$EVAP_RUNNING_INSIDE_TRAVIS" ]] && sudo service apache2 stop

sudo -H -u $USERNAME $ENVDIR/bin/python manage.py dumpdata --natural-foreign --natural-primary --all -e contenttypes -e auth.Permission --indent 2 --output $FILENAME

[[ ! -z "$EVAP_SKIP_CHECKOUT" ]] && echo "Skipping Checkout"
[[ ! -z "$EVAP_SKIP_CHECKOUT" ]] || sudo -H -u $USERNAME git checkout origin/release

sudo -H -u $USERNAME $ENVDIR/bin/pip install -r requirements.txt
# sometimes, this fails for some random i18n test translation files.
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py compilemessages || true
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py collectstatic --noinput
# this fails if debug is set
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py compress --verbosity=0 || true
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py migrate
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py clear_cache
sudo -H -u $USERNAME $ENVDIR/bin/python manage.py refresh_results_cache

[[ -z "$EVAP_RUNNING_INSIDE_TRAVIS" ]] && sudo service apache2 start

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo "Update completed."
