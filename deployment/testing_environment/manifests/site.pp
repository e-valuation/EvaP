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
    package { ['python3', 'python3-dev', 'python3-pip', 'libxslt1-dev', 'zlib1g-dev', 'gettext']:
        ensure => installed,
    } ->
    package { ['nodejs', 'npm']:
        ensure => installed,
    } ->
    exec { "node-symlink":
        provider => shell,
        command => 'ln -f -s /usr/bin/nodejs /usr/bin/node'
    } ->
    exec { "install less":
        provider => shell,
        command => 'npm install -g less'
    }


    class { 'postgresql::globals':
        python_package_name => 'python3'
    } ->
    class { 'postgresql::lib::python':
        package_name => 'python3-psycopg2',
        package_ensure => 'latest'
    }
    class { 'postgresql::server':
    } -> postgresql::server::role { 'evap':
        password_hash  => postgresql_password('evap', 'evap'),
        createdb       => true
    } -> postgresql::server::db { 'evap':
        owner          => 'evap',
        user           => 'evap',
        password       => ''
    } -> package { 'libapache2-mod-wsgi-py3':
        ensure         => latest,
    } -> exec { '/vagrant/requirements.txt':
        provider       => shell,
        command        => 'pip3 --log-file /tmp/pip.log install -r /vagrant/requirements.txt'
    } -> exec { '/vagrant/requirements-dev.txt':
        provider       => shell,
        command        => 'pip3 --log-file /tmp/pip.log install -r /vagrant/requirements-dev.txt'
    } -> class { 'evap':
        db_connector   => 'postgresql_psycopg2'
    }

    # apache environment
    class { 'apache':
        default_vhost => false,
        user          => 'vagrant',
        group         => 'vagrant',
    } ->
    exec {"fix apache's locale":
        provider => shell,
        # this comments in some line in some apache config file to fix the locale.
        # see https://github.com/fsr-itse/EvaP/issues/626
        # and https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/modwsgi/#if-you-get-a-unicodeencodeerror
        command => "sed -i s,#.\\ /etc/default/locale,.\\ /etc/default/locale,g /etc/apache2/envvars"
    }
    class { 'apache::mod::wsgi':
        wsgi_python_path            => '/vagrant'
    } -> apache::vhost { 'evap':
        default_vhost               => true,
        vhost_name                  => '*',
        port                        => '80',
        docroot                     => '/vagrant/evap/static_collected',
        aliases                     => [ { alias => '/static', path => '/vagrant/evap/static_collected' } ],
        wsgi_daemon_process         => 'wsgi',
        wsgi_daemon_process_options => { processes => '2', threads => '15', display-name => '%{GROUP}' },
        wsgi_process_group          => 'wsgi',
        wsgi_script_aliases         => { '/' => '/vagrant/evap/wsgi.py' }
    } -> class { 'apache::mod::expires':
        expires_by_type => [
            { 'text/css' => 'access plus 1 year' },
            { 'text/javascript' => 'access plus 1 year' },
        ]
    }

    exec { 'auto_cd_vagrant':
        provider    => shell,
        command     => 'echo "\ncd /vagrant" >> /home/vagrant/.bashrc'
    }

    exec { 'alias_python_python3':
        provider    => shell,
        # the sudo thing makes "sudo python foo" work
        command     => 'echo "\nalias python=python3\nalias sudo=\'sudo \'" >> /home/vagrant/.bashrc'
    }
}
