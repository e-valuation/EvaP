#!/bin/bash
pushd `dirname $0`/evap
python manage.py migrate && python manage.py collectstatic --noinput && python manage.py compilemessages && /etc/init.d/apache2 restart
popd
