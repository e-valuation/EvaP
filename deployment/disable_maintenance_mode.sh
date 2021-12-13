#!/bin/bash

set -e # abort on error

rm -f /var/www/html/maintenance.css
rm -f /var/www/html/background_gray.svg
rm -f /var/www/html/background_color.svg
rm -f /var/www/html/favicon.png
rm -f /var/www/html/maintenance.html
a2ensite -q evap.conf
a2dissite -q evap-maintenance.conf
service apache2 restart
echo "Maintenance mode disabled."
