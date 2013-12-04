class sshd {

    package { 'openssh-server':
        ensure => latest
    } -> file { 'sshdconfig':
        notify  => Service['ssh'],
        name    => '/etc/ssh/sshd_config',
        owner   => 'root',
        group   => 'root',
        mode    => '0644',
        source  => 'puppet:///modules/sshd/sshd_config'
    } ~> service { 'ssh':
        ensure    => 'running',
        enable    => true
    }
}
