#!/bin/bash
set -e # abort on error
cd `dirname $0`/.. # change to root directory
set -x # print executed commands

sudo -u evap git fetch
sudo -u evap git checkout origin/release
sudo pip3 install -r requirements.txt
sudo -u evap ./manage.py compilemessages
sudo -u evap ./manage.py collectstatic --noinput
sudo -u evap ./manage.py compress --verbosity=0
sudo -u evap ./manage.py migrate
# reload only after static files are updated, so the new code finds all the files it expects.
# also, reload after migrations happened. see https://github.com/fsr-itse/EvaP/pull/817 for a discussion.
sudo service apache2 reload
# update caches. this can take minutes but doesn't need a reload.
sudo -u evap ./manage.py clear_cache
sudo -u evap ./manage.py refresh_results_cache

{ set +x; } 2>/dev/null # don't print the echo command, and don't print the 'set +x' itself

echo Update completed.
