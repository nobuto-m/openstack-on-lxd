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

if [ ! -e ~/ubuntu-16.04-server-cloudimg-amd64-disk1.img ]; then
    wget 'http://cloud-images.ubuntu.com/releases/xenial/release/ubuntu-16.04-server-cloudimg-amd64-disk1.img'
fi

openstack image create --public \
    --container-format=bare \
    --disk-format=qcow2 \
    --min-disk=3 \
    ubuntu-16.04-server-cloudimg-amd64-disk1
