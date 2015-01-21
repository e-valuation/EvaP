# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  # Base box to build off, and download URL for when it doesn't exist on the user's system already
  config.vm.box = "hashicorp/precise64"

  # Create a forwarded port mapping which allows access to a specific port
  # within the machine from a port on the host machine.
  config.vm.network :forwarded_port, guest: 80, host: 8000
  config.vm.network :forwarded_port, guest: 8000, host: 8080

  config.vm.provider :virtualbox do |vb, override|
    vb.customize ["modifyvm", :id, "--memory", "1024"]

    override.vm.box_url = "http://puppet-vagrant-boxes.puppetlabs.com/ubuntu-server-12042-x64-vbox4210.box"
  end

  config.vm.provider :hyperv do |vb, override|
    # setting Hyper-V VM-Memory will be supported in Vagrant 1.7.3
    # as per https://github.com/mitchellh/vagrant/pull/5183

    override.vm.provision "provider-specific", preserve_order:true, type: :shell do |shell|
      shell.path = "deployment/providers/hyperv.sh"
    end
  end

  config.vm.provider :lxc do |v, override|
    override.vm.box_url = "http://bit.ly/vagrant-lxc-precise64-2013-10-23"
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
