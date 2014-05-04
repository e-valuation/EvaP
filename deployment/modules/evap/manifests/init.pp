class evap ($db_connector) {
    $secret_key = random_password(30)
    file { 'evap-localsettings':
        name    => '/vagrant/evap/localsettings.py',
        content  => template('evap/localsettings.py.erb')
    } -> exec { 'django-syncdb':
        provider    => shell,
        command     => 'python manage.py syncdb --noinput --migrate',
        cwd         => '/vagrant'
    } -> exec { 'django-collectstatic':
        provider    => shell,
        command     => 'python manage.py collectstatic --noinput',
        cwd         => '/vagrant'
    }
}
