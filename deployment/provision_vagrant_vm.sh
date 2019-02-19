set -x # print executed commands

# install python stuff
apt-get -q update
apt-get -q install -y python3.7 python3.7-dev python3.7-venv python3-pip gettext

# install sass
apt-get -q install -y sassc
# stay compatible to previous installations with sass
ln -s /usr/bin/sassc /usr/bin/sass

# setup postgres
apt-get -q install -y postgresql
sudo -u postgres createuser --createdb evap
sudo -u postgres psql -U postgres -d postgres -c "ALTER USER evap WITH PASSWORD 'evap';"
sudo -u postgres createdb -O evap evap

# setup redis
apt-get -q install -y redis-server

# install apache
apt-get -q install -y apache2 apache2-dev

# setup virtualenv and mod_wsgi
sudo -H -u vagrant python3.7 -m venv /home/vagrant/venvs/env
sudo -H -u vagrant /home/vagrant/venvs/env/bin/pip install wheel  # required, otherwise following installs fail
sudo -H -u vagrant /home/vagrant/venvs/env/bin/pip install mod_wsgi

# setup apache
a2enmod expires
cp /vagrant/deployment/wsgi.template.conf /etc/apache2/mods-available/wsgi.load
a2enmod wsgi
cp /vagrant/deployment/apache.template.conf /etc/apache2/sites-available/evap.conf
a2ensite evap.conf
a2dissite 000-default.conf
# this comments in some line in some apache config file to fix the locale.
# see https://github.com/fsr-de/EvaP/issues/626
# and https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/modwsgi/#if-you-get-a-unicodeencodeerror
sed -i s,\#.\ /etc/default/locale,.\ /etc/default/locale,g /etc/apache2/envvars
systemctl reload apache2

# auto cd into /vagrant on login and activate venv
echo "cd /vagrant" >> /home/vagrant/.bashrc
echo "source /home/vagrant/venvs/env/bin/activate" >> /home/vagrant/.bashrc

# install requirements
sudo -H -u vagrant /home/vagrant/venvs/env/bin/pip install -r /vagrant/requirements-dev.txt

# deploy localsettings and insert random key
cp /vagrant/deployment/localsettings.template.py /vagrant/evap/localsettings.py
sed -i -e "s/\${SECRET_KEY}/`sudo head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32`/" /vagrant/evap/localsettings.py

# setup evap
cd /vagrant
git submodule update --init
sudo -H -u vagrant /home/vagrant/venvs/env/bin/python manage.py migrate --noinput
sudo -H -u vagrant /home/vagrant/venvs/env/bin/python manage.py collectstatic --noinput
sudo -H -u vagrant /home/vagrant/venvs/env/bin/python manage.py compilemessages
sudo -H -u vagrant /home/vagrant/venvs/env/bin/python manage.py loaddata test_data.json
sudo -H -u vagrant /home/vagrant/venvs/env/bin/python manage.py refresh_results_cache
