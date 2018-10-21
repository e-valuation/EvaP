#!/bin/bash
set -e # abort on error
cd `dirname $0`/.. # change to root directory

sudo -H -u evap git fetch

# Note that apache should not be running during most of the upgrade,
# since then e.g. the backup might be incomplete or the code does not
# match the database layout, or https://github.com/fsr-itse/EvaP/issues/1237.
sudo service apache2 stop

# argument 1 is the filename for the backupfile.
# if no argument is present, no backup will be created.
if [ $# -eq 1 ] # if there is exactly one argument
    then
        echo Creating backup.
        set -x # print executed commands. enable this here to not print the if above.
        sudo -H -u evap ./manage.py dumpdata --indent 2 --output $1
    else
        echo No backup file specified, skipping backup creation.
        set -x # print executed commands
fi

sudo -H -u evap git checkout origin/release
sudo -H -u evap pip3 install --user -r requirements.txt
sudo -H -u evap ./manage.py compilemessages
sudo -H -u evap ./manage.py collectstatic --noinput
sudo -H -u evap ./manage.py compress --verbosity=0
sudo -H -u evap ./manage.py migrate
sudo -H -u evap ./manage.py clear_cache
sudo -H -u evap ./manage.py refresh_results_cache

sudo service apache2 start

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo Update completed.
