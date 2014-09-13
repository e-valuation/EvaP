stage { 'pre':
    before => Stage['main'],
}

node default {
    # update apt
    class { 'apt':
        stage    => pre
    }

    # general packages
    package { ['git', 'build-essential', 'vim']:
        ensure => installed,
    } ->
    # python packages
    package { ['python', 'python-dev', 'python-pip', 'libxml2-dev', 'libxslt-dev', 'python-lxml', 'gettext']:
        ensure => installed,
    } ->
    class { 'postgresql::server':
    } -> postgresql::server::role { 'evap':
        password_hash  => postgresql_password('evap', 'evap'),
        createdb       => true
    } -> postgresql::server::db { 'evap':
        user           => 'evap',
        password       => ''
    } -> package { 'python-psycopg2':
        ensure         => latest,
    } -> exec { '/vagrant/requirements.txt':
        provider       => shell,
        command        => 'pip --log-file /tmp/pip.log install -r /vagrant/requirements.txt'
    } -> exec { '/vagrant/requirements-dev.txt':
        provider       => shell,
        command        => 'pip --log-file /tmp/pip.log install -r /vagrant/requirements-dev.txt'
    } -> class { 'evap':
        db_connector   => 'postgresql_psycopg2'
    }

    # apache environment
    class { 'apache':
        default_vhost => false
    }
    class { 'apache::mod::wsgi':
    } -> apache::vhost { 'evap':
        default_vhost               => true,
        vhost_name                  => '*',
        port                        => '80',
        docroot                     => '/vagrant/evap/staticfiles',
        aliases                     => [ { alias => '/static', path => '/vagrant/evap/staticfiles' } ],
        wsgi_daemon_process         => 'wsgi',
        wsgi_daemon_process_options => { processes => '2', threads => '15', display-name => '%{GROUP}' },
        wsgi_process_group          => 'wsgi',
        wsgi_script_aliases         => { '/' => '/vagrant/handler.wsgi' }
    }
}
