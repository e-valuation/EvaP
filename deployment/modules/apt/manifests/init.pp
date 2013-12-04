class apt {
    exec { 'apt-get update':
        provider => shell,
        command  => 'apt-get update'
    }
}
