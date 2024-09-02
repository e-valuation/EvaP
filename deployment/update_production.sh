#!/usr/bin/env bash

set -e # abort on error
cd "$(dirname "$0")/.." # change to root directory

echo "$PWD"

# used for constructing the backup file name
COMMIT_HASH="$(git rev-parse --short HEAD)"
BACKUP_TITLE="backup"
TIMESTAMP="$(date +%Y-%m-%d_%H:%M:%S)"

# argument 1 is the title for the backupfile.
if [ $# -eq 1 ]
    then
        BACKUP_TITLE=$1
fi

FILENAME="${BACKUP_TITLE}_${TIMESTAMP}_${COMMIT_HASH}.json"

[[ -z "$EVAP_OVERRIDE_BACKUP_FILENAME" ]] || echo "Overriding Automatic Filename"
[[ -z "$EVAP_OVERRIDE_BACKUP_FILENAME" ]] || FILENAME="${BACKUP_TITLE}"

echo "Backup will be stored in $FILENAME"
echo "Starting update..."

set -x # print executed commands. enable this here to not print the if above.

git fetch

./manage.py dumpdata --natural-foreign --natural-primary --all -e contenttypes -e auth.Permission --indent 2 --output "$FILENAME"

[[ ! -z "$EVAP_SKIP_CHECKOUT" ]] && echo "Skipping Checkout"
[[ ! -z "$EVAP_SKIP_CHECKOUT" ]] || git checkout origin/release

# sometimes, this fails for some random i18n test translation files.
./manage.py compilemessages || true
./manage.py scss --production
./manage.py ts compile --fresh
./manage.py collectstatic --noinput
./manage.py migrate
./manage.py clear_cache --all -v=1
./manage.py refresh_results_cache

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo "Update completed."
