#!/bin/bash

#set -e
#set -u
set -x

juju add-model openstack
juju deploy ./bundle-xenial-queens.yaml

juju config keystone admin-password=openstack

time juju wait -w

# forwarders, dnsmasq -> bind -> upstream dns
# TODO: change it to external BIND
#juju config neutron-gateway dns-servers="$(juju run --unit designate-bind/0 unit-get private-address)"
#juju config designate-bind allowed_nets='10.0.0.0/8;172.16.0.0/12;192.168.0.0/16'
#juju config designate-bind forwarders='8.8.8.8;8.8.4.4'

# venv
virtualenv .local/venv
./.local/venv/bin/pip install python-keystoneclient python-neutronclient
. ./.local/venv/bin/activate

. ./openrcv3_project

openstack image create --public --container-format=bare --disk-format=qcow2 xenial \
    --file ~/Downloads/ubuntu-16.04-minimal-cloudimg-amd64-disk1.img

./neutron-ext-net-ksv3 --network-type flat \
    -g 10.0.8.1 -c 10.0.8.0/24 \
    -f 10.0.8.201:10.0.8.254 ext_net

./neutron-tenant-net-ksv3 -p admin -r provider-router \
    internal 192.168.20.0/24

openstack keypair create --public-key ~/.ssh/id_rsa.pub mykey

openstack flavor create --public --ram 512 --disk 0 --ephemeral 0 --vcpus 1 m1.tiny
openstack flavor create --public --ram 1024 --disk 20 --ephemeral 40 --vcpus 1 m1.small
openstack flavor create --public --ram 2048 --disk 40 --ephemeral 40 --vcpus 2 m1.medium
openstack flavor create --public --ram 8192 --disk 40 --ephemeral 40 --vcpus 4 m1.large
openstack flavor create --public --ram 16384 --disk 80 --ephemeral 40 --vcpus 8 m1.xlarge

for i in $(openstack security group list | awk '/default/{ print $2 }'); do \
    openstack security group rule create $i --protocol icmp --remote-ip 0.0.0.0/0; \
    openstack security group rule create $i --protocol tcp --remote-ip 0.0.0.0/0 --dst-port 22; \
done

openstack server create --image xenial --flavor m1.tiny --key-name mykey \
   --wait --nic net-id=$(openstack network list | grep internal | awk '{ print $2 }') \
   openstack-on-lxd-ftw

./float-all

# define non-admin user
openstack project create --domain default my-project
openstack user create \
    --project my-project --project-domain default \
    --domain default \
    --email non-admin@localhost.localdomain \
    --password non-admin \
    non-admin

openstack role add \
    --project my-project --project-domain default \
    --user non-admin --user-domain default \
    Member
