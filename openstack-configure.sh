#!/bin/bash

# set -e
set -u
set -x

. novarc_v3

neutron net-create ext_net \
    --provider:physical_network physnet1 \
    --provider:network_type flat \
    --router:external true

neutron subnet-create ext_net 192.168.1.0/24 \
    --name ext_net_subnet \
    --enable_dhcp false \
    --allocation-pool start=192.168.1.140,end=192.168.1.170 \
    --dns-nameserver 192.168.1.1 --gateway 192.168.1.1

neutron net-create admin_private

neutron subnet-create admin_private 10.0.0.0/24 \
    --name admin_private_subnet \
    --dns-nameserver 192.168.1.1 --gateway 10.0.0.1

neutron router-create admin_router
neutron router-interface-add admin_router admin_private_subnet
neutron router-gateway-set admin_router ext_net


if [ ! -e ~/ubuntu-16.04-server-cloudimg-amd64-disk1.img ]; then
    wget -O ~/ubuntu-16.04-server-cloudimg-amd64-disk1.img \
        'http://cloud-images.ubuntu.com/releases/xenial/release/ubuntu-16.04-server-cloudimg-amd64-disk1.img'
fi

if ! openstack image show ubuntu-16.04-server-cloudimg-amd64-disk1; then
    openstack image create --public \
        --container-format=bare \
        --disk-format=qcow2 \
        --min-disk=3 \
        --file ~/ubuntu-16.04-server-cloudimg-amd64-disk1.img \
        ubuntu-16.04-server-cloudimg-amd64-disk1
fi

openstack flavor create --public --ram 512 --disk 3 --ephemeral 0 --vcpus 1 m1.tiny

if ! openstack server show admin_test_instance; then
    openstack server create \
        --image ubuntu-16.04-server-cloudimg-amd64-disk1 \
        --flavor m1.tiny --key-name mykey \
        --wait --nic net-id="$(neutron net-list | grep -w admin_private | awk '{ print $2 }')" \
        admin_test_instance
fi

openstack security group rule create \
    "$(openstack security group list --project admin | grep default | awk '{ print $2 }')" \
    --protocol icmp --remote-ip 0.0.0.0/0
openstack security group rule create \
    "$(openstack security group list --project admin | grep default | awk '{ print $2 }')" \
    --protocol tcp --remote-ip 0.0.0.0/0 --dst-port 22

if ! openstack server show admin_test_instance | grep -w ext_net; then
    floating_ip=$(openstack floating ip create ext_net | grep -w floating    )
    openstack server add floating ip "$(openstack server list | grep openstack-on-lxd-ftw | awk '{ print $2 }')" "$floating_ip"
fi

openstack console log show --lines 30 admin_test_instance

ping -c 15 "$floating_ip"
