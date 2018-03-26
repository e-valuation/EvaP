# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.require_version ">= 1.8.1"

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/artful64"
  config.vm.box_version = "= 20180102.0.0"

  # port forwarding
  config.vm.network :forwarded_port, guest: 8000, host: 8000 # django server
  config.vm.network :forwarded_port, guest: 80, host: 8001 # apache
  config.vm.network :forwarded_port, guest: 6379, host: 6379 # redis. helpful when developing on windows, for which redis is not available

  config.vm.provider :virtualbox do |v, override|
    # disable logfile
    v.customize [ "modifyvm", :id, "--uartmode1", "disconnected" ]
    # show virtualbox gui, uncomment this to debug startup problems
    #v.gui = true
  end

  config.vm.provision "shell", path: "deployment/provision_vagrant_vm.sh"
end
