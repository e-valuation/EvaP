#! /usr/bin/env bash

set -x # print executed commands

USER="vagrant"
REPO_FOLDER="/opt/evap"
ENV_FOLDER="/home/$USER/venv"

# force apt to not ask, just do defaults.
export DEBIAN_FRONTEND=noninteractive

# install python stuff
apt-get -q update
apt-get -q install -y sudo python3.7 python3.7-dev python3-venv python3.7-venv gettext git wget npm

# setup postgres
printf '#!/bin/sh\nexit 0' > /usr/sbin/policy-rc.d
apt-get -q install -y postgresql
sudo -u postgres createuser --createdb evap
sudo -u postgres psql -U postgres -d postgres -c "ALTER USER evap WITH PASSWORD 'evap';"
sudo -u postgres createdb -O evap evap

# setup redis
apt-get -q install -y redis-server
sudo sed -i "s/bind .*/bind 127.0.0.1/g" /etc/redis/redis.conf
sudo service redis-server restart

# install apache
apt-get -q install -y apache2 apache2-dev

# make user, create home folder, set uid to the same set in the Vagrantfile (required for becoming the synced folder owner), set default shell to bash
#useradd -m -u 501 -s /bin/bash evap
# allow ssh login
#cp -r /home/vagrant/.ssh /home/$USER/.ssh
#chown -R $USER:$USER /home/$USER/.ssh
# allow sudo without password
#echo "$USER ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/evap

# link the mounted evap folder from the home directory
ln -s /evap $REPO_FOLDER

sudo -H -u $USER python3.7 -m venv $ENV_FOLDER
# venv will use ensurepip to install a new version of pip. We need to update that version.
sudo -H -u $USER $ENV_FOLDER/bin/python -m pip install -U pip
sudo -H -u $USER $ENV_FOLDER/bin/pip install wheel
sudo -H -u $USER $ENV_FOLDER/bin/pip install mod_wsgi

# setup apache
a2enmod headers
cp $REPO_FOLDER/deployment/wsgi.template.conf /etc/apache2/mods-available/wsgi.load
sed -i -e "s=\${ENV_FOLDER}=$ENV_FOLDER=" /etc/apache2/mods-available/wsgi.load # note this uses '=' as alternate delimiter
a2enmod wsgi
cp $REPO_FOLDER/deployment/apache.template.conf /etc/apache2/sites-available/evap.conf
sed -i -e "s=\${ENV_FOLDER}=$ENV_FOLDER=" /etc/apache2/sites-available/evap.conf
sed -i -e "s=\${REPO_FOLDER}=$REPO_FOLDER=" /etc/apache2/sites-available/evap.conf
a2ensite evap.conf
a2dissite 000-default.conf
# this comments in some line in some apache config file to fix the locale.
# see https://github.com/e-valuation/EvaP/issues/626
# and https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/modwsgi/#if-you-get-a-unicodeencodeerror
sed -i s,\#.\ /etc/default/locale,.\ /etc/default/locale,g /etc/apache2/envvars
service apache2 reload

cp /etc/skel/.bashrc /home/$USER/
# auto cd into /$USER on login and activate venv
echo "cd $REPO_FOLDER" >> /home/$USER/.bashrc
echo "source $ENV_FOLDER/bin/activate" >> /home/$USER/.bashrc

# install requirements
sudo -H -u $USER $ENV_FOLDER/bin/pip install -r $REPO_FOLDER/requirements-dev.txt

# deploy localsettings and insert random key
cp $REPO_FOLDER/deployment/localsettings.template.py $REPO_FOLDER/evap/localsettings.py
sed -i -e "s/\${SECRET_KEY}/$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)/" $REPO_FOLDER/evap/localsettings.py

# setup vm auto-completion
#cp $REPO_FOLDER/deployment/manage_autocompletion.sh /etc/bash_completion.d/

# install libraries for puppeteer
apt-get -q install -y libasound2 libgconf-2-4 libgbm1 libgtk-3-0 libnss3 libx11-xcb1 libxss1 libxshmfence-dev

# install nvm
wget https://raw.githubusercontent.com/nvm-sh/nvm/v0.38.0/install.sh --no-verbose --output-document - | sudo -H -u $USER bash

# setup evap
cd /evap
git submodule update --init
sudo -H -u $USER bash -c "source /home/$USER/.nvm/nvm.sh; nvm install --no-progress node; npm ci"
echo "nvm use node" >> /home/$USER/.bashrc
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py migrate --noinput
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py collectstatic --noinput
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py compilemessages --locale de_DE --locale en_US
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py loaddata test_data.json
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py refresh_results_cache
