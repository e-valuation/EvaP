#! /usr/bin/env bash

set -x # print executed commands

MOUNTPOINT="/evap"
USER="evap"
REPO_FOLDER="/opt/evap"
ENV_FOLDER="/home/$USER/venv"
NODE_MODULES_FOLDER="/home/$USER/node_modules"
EVAP_PYTHON=python3.10

# force apt to not ask, just do defaults.
export DEBIAN_FRONTEND=noninteractive

apt-get -q update

# system utilities that docker containers don't have
apt-get -q install -y sudo wget git bash-completion software-properties-common
# docker weirdly needs this -- see https://stackoverflow.com/questions/46247032/how-to-solve-invoke-rc-d-policy-rc-d-denied-execution-of-start-when-building
printf '#!/bin/sh\nexit 0' > /usr/sbin/policy-rc.d

# install python stuff
apt-get -q install -y $EVAP_PYTHON $EVAP_PYTHON-dev $EVAP_PYTHON-venv gettext

# setup postgres
apt-get -q install -y postgresql
sudo -u postgres createuser --createdb evap
sudo -u postgres psql -U postgres -d postgres -c "ALTER USER evap WITH PASSWORD 'evap';"
sudo -u postgres createdb -O evap evap

# setup redis
apt-get -q install -y redis-server
sed -i "s/^bind .*/bind 127.0.0.1/g" /etc/redis/redis.conf
service redis-server restart

# install apache
apt-get -q install -y apache2 apache2-dev libapache2-mod-wsgi-py3

# With docker for mac, root will own the mount point (uid=0). chmod does not touch the host file system in these cases.
OWNER=$(stat -c %U "$MOUNTPOINT/evap")
if [ "$OWNER" == "root" ]; then chown -R 1042 "$MOUNTPOINT"; fi

# make user, create home folder, set uid to the same set in the Vagrantfile (required for becoming the synced folder owner), set default shell to bash
useradd -m -u $(stat -c "%u" "$MOUNTPOINT/evap") -s /bin/bash evap
# allow ssh login
cp -r /home/vagrant/.ssh /home/$USER/.ssh
chown -R $USER:$USER /home/$USER/.ssh
# allow sudo without password
echo "$USER ALL=(ALL) NOPASSWD:ALL" | tee /etc/sudoers.d/evap

# link the mounted evap folder from the home directory
ln -s "$MOUNTPOINT" "$REPO_FOLDER"

sudo -H -u $USER $EVAP_PYTHON -m venv $ENV_FOLDER
# venv will use ensurepip to install a new version of pip. We need to update that version.
sudo -H -u $USER $ENV_FOLDER/bin/python -m pip install -U pip
sudo -H -u $USER $ENV_FOLDER/bin/pip install wheel

# setup apache
a2enmod headers
a2enmod wsgi
a2enmod rewrite
cp $REPO_FOLDER/deployment/apache.maintenance-template.conf /etc/apache2/sites-available/evap-maintenance.conf
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

# required for docker (no-op if already started)
echo "sudo service postgresql start && sudo service redis-server start" >> /home/$USER/.bashrc

# install requirements
sudo -H -u $USER $ENV_FOLDER/bin/pip install -r $REPO_FOLDER/requirements-dev.txt

# deploy localsettings and insert random key
cp $REPO_FOLDER/deployment/localsettings.template.py $REPO_FOLDER/evap/localsettings.py
sed -i -e "s/\${SECRET_KEY}/$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)/" $REPO_FOLDER/evap/localsettings.py

# setup vm auto-completion
cp $REPO_FOLDER/deployment/manage_autocompletion.sh /etc/bash_completion.d/

# install firefox and geckodriver
sudo install -d -m 0755 /etc/apt/keyrings
wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" | sudo tee -a /etc/apt/sources.list.d/mozilla.list > /dev/null
echo '
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 1000
' | sudo tee /etc/apt/preferences.d/mozilla 
apt update
apt -q install -y firefox

wget https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz -O geckodriver.tar.gz
tar xzf geckodriver.tar.gz -C /usr/local/bin/
chmod +x /usr/local/bin/geckodriver

# install nvm
wget https://raw.githubusercontent.com/nvm-sh/nvm/v0.38.0/install.sh --no-verbose --output-document - | sudo -H -u $USER bash

# setup evap
cd "$MOUNTPOINT"
sudo -H -u $USER git submodule update --init

sudo -H -u $USER mkdir node_modules
sudo -H -u $USER mkdir ${NODE_MODULES_FOLDER}
sudo mount --bind ${NODE_MODULES_FOLDER} ${MOUNTPOINT}/node_modules
echo "sudo mount --bind ${NODE_MODULES_FOLDER} ${MOUNTPOINT}/node_modules" >> /home/$USER/.bashrc

sudo -H -u $USER bash -c "source /home/$USER/.nvm/nvm.sh; nvm install --no-progress node; npm ci"
echo "nvm use node" >> /home/$USER/.bashrc

sudo -H -u $USER $ENV_FOLDER/bin/python manage.py migrate --noinput
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py collectstatic --noinput
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py compilemessages --locale de
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py loaddata test_data.json
sudo -H -u $USER $ENV_FOLDER/bin/python manage.py refresh_results_cache
