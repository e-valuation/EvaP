class evap ($db_connector) {
    $secret_key = random_password(30)
    file { 'evap-localsettings':
        name    => '/vagrant/evap/localsettings.py',
        content  => template('evap/localsettings.py.erb')
    } -> exec { 'django-migrate':
        provider    => shell,
        command     => 'python3 manage.py migrate --noinput',
        cwd         => '/vagrant'
    } -> exec { 'django-collectstatic':
        provider    => shell,
        command     => 'python3 manage.py collectstatic --noinput',
        cwd         => '/vagrant'
    } -> exec { 'django-compilemessages':
        provider    => shell,
        command     => 'python3 manage.py compilemessages',
        cwd         => '/vagrant'
    } -> exec { 'evap-load-testdata':
        provider    => shell,
        command     => 'python3 manage.py loaddata test_data.json',
        cwd         => '/vagrant'
    } -> exec { 'evap-createcachetable':
        provider    => shell,
        command     => 'python3 manage.py createcachetable',
        cwd         => '/vagrant'
    }
}
