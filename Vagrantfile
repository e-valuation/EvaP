# -*- mode: ruby -*-
# vi: set ft=ruby :

# needed for the hyper-v stuff
Vagrant.require_version ">= 1.7.0"

Vagrant.configure("2") do |config|
  config.vm.box = "puppetlabs/ubuntu-14.04-64-puppet"

  # port forwarding for the http server and for pycharm
  config.vm.network :forwarded_port, guest: 80, host: 8000
  config.vm.network :forwarded_port, guest: 8000, host: 8080

  # uncomment this to debug startup problems
  #config.vm.provider :virtualbox do |v, override|
  #  v.gui = true
  #end

  config.vm.provider :hyperv do |vb, override|
    override.vm.provision "provider-specific", preserve_order:true, type: :shell do |shell|
      shell.path = "deployment/providers/hyperv.sh"
    end
  end

  # This is a placeholder job that can be overridden in order to install
  # puppet if needed *before* the actual provisioning happens
  config.vm.provision "provider-specific", type: :shell do |shell|
    shell.path = "deployment/providers/default.sh"
  end

  config.vm.provision :puppet do |puppet|
    puppet.module_path = "deployment/modules"
    puppet.manifests_path = "deployment"
    puppet.manifest_file = "site.pp"
  end
end
