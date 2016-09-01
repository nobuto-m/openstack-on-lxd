Overview
========

This charm provides Keystone, the Openstack identity service. It's target
platform is (ideally) Ubuntu LTS + Openstack.

Usage
=====

The following interfaces are provided:

    - nrpe-external-master: Used to generate Nagios checks.

    - identity-service: Openstack API endpoints request an entry in the 
      Keystone service catalog + endpoint template catalog. When a relation
      is established, Keystone receives: service name, region, public_url,
      admin_url and internal_url. It first checks that the requested service
      is listed as a supported service. This list should stay updated to
      support current Openstack core services. If the service is supported,
      an entry in the service catalog is created, an endpoint template is
      created and a admin token is generated. The other end of the relation
      receives the token as well as info on which ports Keystone is listening
      on.

    - keystone-service: This is currently only used by Horizon/dashboard
      as its interaction with Keystone is different from other Openstack API
      services. That is, Horizon requests a Keystone role and token exists.
      During a relation, Horizon requests its configured default role and
      Keystone responds with a token and the auth + admin ports on which
      Keystone is listening.

    - identity-admin: Charms use this relation to obtain the credentials
      for the admin user. This is intended for charms that automatically
      provision users, tenants, etc. or that otherwise automate using the
      Openstack cluster deployment.

    - identity-notifications: Used to broadcast messages to any services
      listening on the interface.

    - identity-credentials: Charms use this relation to obtain keystone
      credentials without creating a service catalog entry. Set 'username'
      only on the relation and keystone will set defaults and return
      authentication details. Possible relation settings:
        username: Username to be created.
        project: Project (tenant) name to be created. Defaults to services
                 project.
        requested_roles: Comma delimited list of roles to be created
        requested_grants: Comma delimited list of roles to be granted.
                          Defaults to Admin role.
        domain: Keystone v3 domain the user will be created in. Defaults
                to the Default domain.

Database
--------

Keystone requires a database. By default, a local sqlite database is used.
The charm supports relations to a shared-db via mysql-shared interface. When
a new data store is configured, the charm ensures the minimum administrator
credentials exist (as configured via charm configuration)

HA/Clustering
-------------

There are two mutually exclusive high availability options: using virtual
IP(s) or DNS. In both cases, a relationship to hacluster is required which
provides the corosync back end HA functionality.

To use virtual IP(s) the clustered nodes must be on the same subnet such that
the VIP is a valid IP on the subnet for one of the node's interfaces and each
node has an interface in said subnet. The VIP becomes a highly-available API
endpoint.

At a minimum, the config option 'vip' must be set in order to use virtual IP
HA. If multiple networks are being used, a VIP should be provided for each
network, separated by spaces. Optionally, vip_iface or vip_cidr may be
specified.

To use DNS high availability there are several prerequisites. However, DNS HA
does not require the clustered nodes to be on the same subnet.
Currently the DNS HA feature is only available for MAAS 2.0 or greater
environments. MAAS 2.0 requires Juju 2.0 or greater. The clustered nodes must
have static or "reserved" IP addresses registered in MAAS. The DNS hostname(s)
must be pre-registered in MAAS before use with DNS HA.

At a minimum, the config option 'dns-ha' must be set to true and at least one
of 'os-public-hostname', 'os-internal-hostname' or 'os-internal-hostname' must
be set in order to use DNS HA. One or more of the above hostnames may be set.

The charm will throw an exception in the following circumstances:
If neither 'vip' nor 'dns-ha' is set and the charm is related to hacluster
If both 'vip' and 'dns-ha' are set as they are mutually exclusive
If 'dns-ha' is set and none of the os-{admin,internal,public}-hostname(s) are set

SSL/HTTPS
---------

This charm also supports SSL and HTTPS endpoints. In order to ensure SSL
certificates are only created once and distributed to all units, one unit gets
elected as an ssl-cert-master. One side-effect of this is that as units are
scaled-out the currently elected leader needs to be running in order for nodes
to sync certificates. This 'feature' is to work around the lack of native
leadership election via Juju itself, a feature that is due for release some
time soon but until then we have to rely on this. Also, if a keystone unit does
go down, it must be removed from Juju i.e.

    juju destroy-unit keystone/<unit-num>

Otherwise it will be assumed that this unit may come back at some point and
therefore must be know to be in-sync with the rest before continuing.

Network Space support
---------------------

This charm supports the use of Juju Network Spaces, allowing the charm to be bound to network space configurations managed directly by Juju.  This is only supported with Juju 2.0 and above.

API endpoints can be bound to distinct network spaces supporting the network separation of public, internal and admin endpoints.

Access to the underlying MySQL instance can also be bound to a specific space using the shared-db relation.

To use this feature, use the --bind option when deploying the charm:

    juju deploy keystone --bind "public=public-space internal=internal-space admin=admin-space shared-db=internal-space"

alternatively these can also be provided as part of a juju native bundle configuration:

    keystone:
      charm: cs:xenial/keystone
      num_units: 1
      bindings:
        public: public-space
        admin: admin-space
        internal: internal-space
        shared-db: internal-space

NOTE: Spaces must be configured in the underlying provider prior to attempting to use them.

NOTE: Existing deployments using os-*-network configuration options will continue to function; these options are preferred over any network space binding provided if set.

