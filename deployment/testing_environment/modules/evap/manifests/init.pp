class evap ($db_connector) {
    $secret_key = random_password(30)
    file { 'evap-localsettings':
        name    => '/vagrant/evap/localsettings.py',
        content  => template('evap/localsettings.py.erb')
    } -> exec { 'django-migrate':
        provider    => shell,
        command     => 'python3 manage.py migrate --noinput',
        user        => 'vagrant',
        cwd         => '/vagrant'
    } -> exec { 'django-collectstatic':
        provider    => shell,
        command     => 'python3 manage.py collectstatic --noinput',
        user        => 'vagrant',
        cwd         => '/vagrant'
    } -> exec { 'django-compilemessages':
        provider    => shell,
        command     => 'python3 manage.py compilemessages',
        user        => 'vagrant',
        cwd         => '/vagrant'
    } -> exec { 'evap-load-testdata':
        provider    => shell,
        command     => 'python3 manage.py loaddata test_data.json',
        user        => 'vagrant',
        cwd         => '/vagrant'
    } -> exec { 'evap-createcachetable':
        provider    => shell,
        command     => 'python3 manage.py createcachetable',
        user        => 'vagrant',
        cwd         => '/vagrant'
    } -> exec { 'evap-cache-warmup':
        provider    => shell,
        command     => 'python3 manage.py refresh_results_cache',
        user        => 'vagrant',
        cwd         => '/vagrant'
    }
}
