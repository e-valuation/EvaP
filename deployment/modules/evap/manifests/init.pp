class evap ($db_connector) {
    $secret_key = random_password(30)
    file { 'evap-localsettings':
        name    => '/vagrant/evap/localsettings.py',
        content  => template('evap/localsettings.py.erb')
    } -> exec { 'django-migrate':
        provider    => shell,
        command     => 'python manage.py migrate --noinput',
        cwd         => '/vagrant'
    } -> exec { 'django-collectstatic':
        provider    => shell,
        command     => 'python manage.py collectstatic --noinput',
        cwd         => '/vagrant'
    } -> exec { 'evap-load-testdata':
        provider    => shell,
        command     => 'python manage.py loaddata test_data.json',
        cwd         => '/vagrant'
    }
}
