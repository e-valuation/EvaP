#!/bin/bash
set -e # abort on error
cd "$(dirname "$0")/.." # change to root directory

echo "$PWD"

# used for constructing the backup file name
COMMIT_HASH="$(git rev-parse --short HEAD)"
BACKUP_TITLE="backup"
TIMESTAMP="$(date +%Y-%m-%d_%H:%M:%S)"

USERNAME="evap"
ENVDIR="/opt/evap/env"
[[ ! -z "$GITHUB_WORKFLOW" ]] && echo "Detected GitHub" && USERNAME="root" && ENVDIR="${VIRTUAL_ENV}"

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

sudo -H -u $USERNAME git fetch

# Note that apache should not be running during most of the upgrade,
# since then e.g. the backup might be incomplete or the code does not
# match the database layout, or https://github.com/e-valuation/EvaP/issues/1237.
[[ -z "$GITHUB_WORKFLOW" ]] && sudo ./deployment/enable_maintenance_mode.sh

sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py dumpdata --natural-foreign --natural-primary --all -e contenttypes -e auth.Permission --indent 2 --output "$FILENAME"

[[ ! -z "$EVAP_SKIP_CHECKOUT" ]] && echo "Skipping Checkout"
[[ ! -z "$EVAP_SKIP_CHECKOUT" ]] || sudo -H -u "$USERNAME" git checkout origin/release

sudo -H -u "$USERNAME" "$ENVDIR/bin/pip" install -r requirements.txt
# sometimes, this fails for some random i18n test translation files.
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py compilemessages || true
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py scss --production || true
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py ts compile --fresh || true
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py collectstatic --noinput
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py migrate
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py clear_cache --all -v=1
sudo -H -u "$USERNAME" "$ENVDIR/bin/python" manage.py refresh_results_cache

[[ -z "$GITHUB_WORKFLOW" ]] && sudo ./deployment/disable_maintenance_mode.sh

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo "Update completed."
