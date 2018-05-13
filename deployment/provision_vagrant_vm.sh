set -x # print executed commands

# install python stuff
apt-get -q update
apt-get -q install -y python3-dev python3-pip gettext

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

# setup apache
apt-get -q install -y apache2 libapache2-mod-wsgi-py3
a2enmod expires
cp /vagrant/deployment/apache.template.conf /etc/apache2/sites-available/evap.conf
a2ensite evap.conf
a2dissite 000-default.conf
# this comments in some line in some apache config file to fix the locale.
# see https://github.com/fsr-itse/EvaP/issues/626
# and https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/modwsgi/#if-you-get-a-unicodeencodeerror
sed -i s,\#.\ /etc/default/locale,.\ /etc/default/locale,g /etc/apache2/envvars
systemctl reload apache2

# alias python -> python3
echo "alias python=python3" >> /home/vagrant/.bashrc

# auto cd into /vagrant on login
echo "cd /vagrant" >> /home/vagrant/.bashrc

# install requirements
sudo -H -u vagrant pip3 install --user -r /vagrant/requirements-dev.txt

# deploy localsettings and insert random key
cp /vagrant/deployment/localsettings.template.py /vagrant/evap/localsettings.py
sed -i -e "s/\${SECRET_KEY}/`sudo head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32`/" /vagrant/evap/localsettings.py

# setup evap
cd /vagrant
git submodule update --init
sudo -H -u vagrant python3 manage.py migrate --noinput
sudo -H -u vagrant python3 manage.py collectstatic --noinput
sudo -H -u vagrant python3 manage.py compilemessages
sudo -H -u vagrant python3 manage.py loaddata test_data.json
sudo -H -u vagrant python3 manage.py createcachetable
sudo -H -u vagrant python3 manage.py refresh_results_cache
