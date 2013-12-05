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
    }

    # configure mysql
    class { '::mysql::server':
        root_password => '7FzSCogWAFCt'
    } -> mysql::db { 'evap':
        user          => 'evap',
        password      => '0Am5dWVSC9kd',
    } ->
    # python environment
    package { ['python', 'python-dev', 'python-pip', 'python-imaging', 'python-lxml', 'python-mysqldb', 'libxml2-dev', 'libxslt-dev']:
        ensure => latest,
        require => Package['build-essential']
    } -> exec { '/vagrant/requirements.txt':
        provider    => shell,
        command     => 'pip --log-file /tmp/pip.log install -r /vagrant/requirements.txt'
    } -> class { 'evap': }

    # apache environment
    class { 'apache': 
        default_vhost => false
    }
    class { 'apache::mod::wsgi':
    }
    apache::vhost { 'evap':
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
