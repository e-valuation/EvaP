#!/bin/bash
set -e
pushd `dirname $0`
ssh-agent bash -c "ssh-add deployment_key; git pull"
pushd `dirname $0`/evap
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages
popd
popd
service apache2 restart
echo Update completed.
