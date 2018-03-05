#!/bin/bash

set -e
set -u

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
