# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.require_version ">= 1.8.1"

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/bionic64"
  config.vm.box_version = "= 20190621.0.0 "

  # port forwarding
  config.vm.network :forwarded_port, guest: 8000, host: 8000 # django server
  config.vm.network :forwarded_port, guest: 80, host: 8001 # apache
  config.vm.network :forwarded_port, guest: 6379, host: 6379 # redis. helpful when developing on windows, for which redis is not available

  config.vm.provider :virtualbox do |v, override|
    # disable logfile
    if Vagrant::Util::Platform.windows?
      v.customize [ "modifyvm", :id, "--uartmode1", "file", "nul" ]
    else
      v.customize [ "modifyvm", :id, "--uartmode1", "file", "/dev/null" ]
    end

    # show virtualbox gui, uncomment this to debug startup problems
    #v.gui = true
  end

  # override username to be evap instead of vagrant, just as it is on production.
  # This is necessary so management script can assume evap is the correct user to
  # execute stuff as.
  # Mounting with uid and gid is necessary as the provision script will create
  # this user, so mounting before does not work with an owner specified by name.
  # Also, provision needs to use vagrant as ssh user (since evap does not exist yet)
  config.vm.synced_folder ".", "/evap", mount_options: ["uid=1042", "gid=1042"]
  if ARGV[0] == "ssh"
    config.ssh.username = 'evap'
  end

  config.vm.provision "shell", path: "deployment/provision_vagrant_vm.sh"
end
