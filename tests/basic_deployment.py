#!/usr/bin/python
#
# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Basic keystone amulet functional tests.
"""

import amulet
import os
import yaml

from charmhelpers.contrib.openstack.amulet.deployment import (
    OpenStackAmuletDeployment
)

from charmhelpers.contrib.openstack.amulet.utils import (
    OpenStackAmuletUtils,
    DEBUG,
    # ERROR
)
import keystoneclient
from charmhelpers.core.decorators import retry_on_exception

# Use DEBUG to turn on debug logging
u = OpenStackAmuletUtils(DEBUG)


class KeystoneBasicDeployment(OpenStackAmuletDeployment):
    """Amulet tests on a basic keystone deployment."""

    def __init__(self, series=None, openstack=None,
                 source=None, git=False, stable=True):
        """Deploy the entire test environment."""
        super(KeystoneBasicDeployment, self).__init__(series, openstack,
                                                      source, stable)
        self.keystone_api_version = 2
        self.git = git
        self._add_services()
        self._add_relations()
        self._configure_services()
        self._deploy()

        u.log.info('Waiting on extended status checks...')
        self.exclude_services = ['mysql']
        self._auto_wait_for_status(exclude_services=self.exclude_services)

        self._initialize_tests()

    def _assert_services(self, should_run):
        if self.is_liberty_or_newer():
            services = ("apache2", "haproxy")
        else:
            services = ("keystone-all", "apache2", "haproxy")
        u.get_unit_process_ids(
            {self.keystone_sentry: services}, expect_success=should_run)

    def _add_services(self):
        """Add services

           Add the services that we're testing, where keystone is local,
           and the rest of the service are from lp branches that are
           compatible with the local charm (e.g. stable or next).
           """
        this_service = {'name': 'keystone'}
        other_services = [{'name': 'mysql'},
                          {'name': 'rabbitmq-server'},  # satisfy wrkload stat
                          {'name': 'cinder'}]
        super(KeystoneBasicDeployment, self)._add_services(this_service,
                                                           other_services)

    def _add_relations(self):
        """Add all of the relations for the services."""
        relations = {'keystone:shared-db': 'mysql:shared-db',
                     'cinder:shared-db': 'mysql:shared-db',
                     'cinder:amqp': 'rabbitmq-server:amqp',
                     'cinder:identity-service': 'keystone:identity-service'}
        super(KeystoneBasicDeployment, self)._add_relations(relations)

    def _configure_services(self):
        """Configure all of the services."""
        keystone_config = {'admin-password': 'openstack',
                           'admin-token': 'ubuntutesting',
                           'preferred-api-version': self.keystone_api_version}
        if self.git:
            amulet_http_proxy = os.environ.get('AMULET_HTTP_PROXY')

            reqs_repo = 'git://github.com/openstack/requirements'
            keystone_repo = 'git://github.com/openstack/keystone'
            if self._get_openstack_release() == self.trusty_icehouse:
                reqs_repo = 'git://github.com/coreycb/requirements'
                keystone_repo = 'git://github.com/coreycb/keystone'

            branch = 'stable/' + self._get_openstack_release_string()

            openstack_origin_git = {
                'repositories': [
                    {'name': 'requirements',
                     'repository': reqs_repo,
                     'branch': branch},
                    {'name': 'keystone',
                     'repository': keystone_repo,
                     'branch': branch},
                ],
                'directory': '/mnt/openstack-git',
                'http_proxy': amulet_http_proxy,
                'https_proxy': amulet_http_proxy,
            }
            keystone_config['openstack-origin-git'] = \
                yaml.dump(openstack_origin_git)

        mysql_config = {'dataset-size': '50%'}
        cinder_config = {'block-device': 'None'}
        configs = {
            'keystone': keystone_config,
            'mysql': mysql_config,
            'cinder': cinder_config
        }
        super(KeystoneBasicDeployment, self)._configure_services(configs)

    @retry_on_exception(5, base_delay=10)
    def set_api_version(self, api_version):
        set_alternate = {'preferred-api-version': api_version}

        # Make config change, check for service restarts
        u.log.debug('Setting preferred-api-version={}'.format(api_version))
        self.d.configure('keystone', set_alternate)
        self.keystone_api_version = api_version
        client = self.get_keystone_client(api_version=api_version)
        # List an artefact that needs authorisation to check admin user
        # has been setup. If that is still in progess
        # keystoneclient.exceptions.Unauthorized will be thrown and caught by
        # @retry_on_exception
        if api_version == 2:
            client.tenants.list()
            self.keystone_v2 = self.get_keystone_client(api_version=2)
        else:
            client.projects.list()
            self.keystone_v3 = self.get_keystone_client(api_version=3)

    def get_keystone_client(self, api_version=None):
        if api_version == 2:
            return u.authenticate_keystone_admin(self.keystone_sentry,
                                                 user='admin',
                                                 password='openstack',
                                                 tenant='admin',
                                                 api_version=api_version,
                                                 keystone_ip=self.keystone_ip)
        else:
            return u.authenticate_keystone_admin(self.keystone_sentry,
                                                 user='admin',
                                                 password='openstack',
                                                 api_version=api_version,
                                                 keystone_ip=self.keystone_ip)

    def create_users_v2(self):
        # Create a demo tenant/role/user
        self.demo_tenant = 'demoTenant'
        self.demo_role = 'demoRole'
        self.demo_user = 'demoUser'
        if not u.tenant_exists(self.keystone_v2, self.demo_tenant):
            tenant = self.keystone_v2.tenants.create(
                tenant_name=self.demo_tenant,
                description='demo tenant',
                enabled=True)
            self.keystone_v2.roles.create(name=self.demo_role)
            self.keystone_v2.users.create(name=self.demo_user,
                                          password='password',
                                          tenant_id=tenant.id,
                                          email='demo@demo.com')

            # Authenticate keystone demo
            self.keystone_demo = u.authenticate_keystone_user(
                self.keystone_v2, user=self.demo_user,
                password='password', tenant=self.demo_tenant)

    def create_users_v3(self):
        # Create a demo tenant/role/user
        self.demo_project = 'demoProject'
        self.demo_user_v3 = 'demoUserV3'
        self.demo_domain = 'demoDomain'
        try:
            domain = self.keystone_v3.domains.find(name=self.demo_domain)
        except keystoneclient.exceptions.NotFound:
            domain = self.keystone_v3.domains.create(
                self.demo_domain,
                description='Demo Domain',
                enabled=True
            )

        try:
            self.keystone_v3.projects.find(name=self.demo_project)
        except keystoneclient.exceptions.NotFound:
            self.keystone_v3.projects.create(
                self.demo_project,
                domain,
                description='Demo Project',
                enabled=True,
            )

        try:
            self.keystone_v3.roles.find(name=self.demo_role)
        except keystoneclient.exceptions.NotFound:
            self.keystone_v3.roles.create(name=self.demo_role)

        try:
            self.keystone_v3.users.find(name=self.demo_user_v3)
        except keystoneclient.exceptions.NotFound:
            self.keystone_v3.users.create(
                self.demo_user_v3,
                domain=domain.id,
                project=self.demo_project,
                password='password',
                email='demov3@demo.com',
                description='Demo',
                enabled=True)

    def _initialize_tests(self):
        """Perform final initialization before tests get run."""
        # Access the sentries for inspecting service units
        self.mysql_sentry = self.d.sentry['mysql'][0]
        self.keystone_sentry = self.d.sentry['keystone'][0]
        self.cinder_sentry = self.d.sentry['cinder'][0]
        u.log.debug('openstack release val: {}'.format(
            self._get_openstack_release()))
        u.log.debug('openstack release str: {}'.format(
            self._get_openstack_release_string()))
        self.keystone_ip = self.keystone_sentry.relation(
            'shared-db',
            'mysql:shared-db')['private-address']
        self.set_api_version(2)
        # Authenticate keystone admin
        self.keystone_v2 = self.get_keystone_client(api_version=2)
        self.keystone_v3 = self.get_keystone_client(api_version=3)
        self.create_users_v2()

    def test_100_services(self):
        """Verify the expected services are running on the corresponding
           service units."""
        services = {
            self.mysql_sentry: ['mysql'],
            self.keystone_sentry: ['keystone'],
            self.cinder_sentry: ['cinder-api',
                                 'cinder-scheduler',
                                 'cinder-volume']
        }
        if self.is_liberty_or_newer():
            services[self.keystone_sentry] = ['apache2']
        else:
            services[self.keystone_sentry] = ['keystone']
        ret = u.validate_services_by_name(services)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def validate_keystone_tenants(self, client):
        """Verify all existing tenants."""
        u.log.debug('Checking keystone tenants...')
        expected = [
            {'name': 'services',
             'enabled': True,
             'description': 'Created by Juju',
             'id': u.not_null},
            {'name': 'demoTenant',
             'enabled': True,
             'description': 'demo tenant',
             'id': u.not_null},
            {'name': 'admin',
             'enabled': True,
             'description': 'Created by Juju',
             'id': u.not_null}
        ]
        if self.keystone_api_version == 2:
            actual = client.tenants.list()
        else:
            actual = client.projects.list()

        ret = u.validate_tenant_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_102_keystone_tenants(self):
        self.set_api_version(2)
        self.validate_keystone_tenants(self.keystone_v2)

    def validate_keystone_roles(self, client):
        """Verify all existing roles."""
        u.log.debug('Checking keystone roles...')
        expected = [
            {'name': 'demoRole',
             'id': u.not_null},
            {'name': 'Admin',
             'id': u.not_null}
        ]
        actual = client.roles.list()

        ret = u.validate_role_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_104_keystone_roles(self):
        self.set_api_version(2)
        self.validate_keystone_roles(self.keystone_v2)

    def validate_keystone_users(self, client):
        """Verify all existing roles."""
        u.log.debug('Checking keystone users...')
        base = [
            {'name': 'demoUser',
             'enabled': True,
             'id': u.not_null,
             'email': 'demo@demo.com'},
            {'name': 'admin',
             'enabled': True,
             'id': u.not_null,
             'email': 'juju@localhost'},
            {'name': 'cinder_cinderv2',
             'enabled': True,
             'id': u.not_null,
             'email': u'juju@localhost'}
        ]
        expected = []
        for user_info in base:
            if self.keystone_api_version == 2:
                user_info['tenantId'] = u.not_null
            else:
                user_info['default_project_id'] = u.not_null
            expected.append(user_info)
        actual = client.users.list()
        ret = u.validate_user_data(expected, actual,
                                   api_version=self.keystone_api_version)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_106_keystone_users(self):
        self.set_api_version(2)
        self.validate_keystone_users(self.keystone_v2)

    def is_liberty_or_newer(self):
        os_release = self._get_openstack_release_string()
        if os_release >= 'liberty':
            return True
        else:
            u.log.info('Skipping test, {} < liberty'.format(os_release))
            return False

    def test_112_keystone_tenants(self):
        if self.is_liberty_or_newer():
            self.set_api_version(3)
            self.validate_keystone_tenants(self.keystone_v3)

    def test_114_keystone_tenants(self):
        if self.is_liberty_or_newer():
            self.set_api_version(3)
            self.validate_keystone_roles(self.keystone_v3)

    def test_116_keystone_users(self):
        if self.is_liberty_or_newer():
            self.set_api_version(3)
            self.validate_keystone_users(self.keystone_v3)

    def test_118_keystone_users(self):
        if self.is_liberty_or_newer():
            self.set_api_version(3)
            self.create_users_v3()
            actual_user = self.keystone_v3.users.find(name=self.demo_user_v3)
            expect = {
                'default_project_id': self.demo_project,
                'email': 'demov3@demo.com',
                'name': self.demo_user_v3,
            }
            for key in expect.keys():
                u.log.debug('Checking user {} {} is {}'.format(
                    self.demo_user_v3,
                    key,
                    expect[key])
                )
                assert expect[key] == getattr(actual_user, key)

    def test_120_keystone_domains(self):
        if self.is_liberty_or_newer():
            self.set_api_version(3)
            self.create_users_v3()
            actual_domain = self.keystone_v3.domains.find(
                name=self.demo_domain
            )
            expect = {
                'name': self.demo_domain,
            }
            for key in expect.keys():
                u.log.debug('Checking domain {} {} is {}'.format(
                    self.demo_domain,
                    key,
                    expect[key])
                )
                assert expect[key] == getattr(actual_domain, key)

    def test_138_service_catalog(self):
        """Verify that the service catalog endpoint data is valid."""
        u.log.debug('Checking keystone service catalog...')
        self.set_api_version(2)
        endpoint_check = {
            'adminURL': u.valid_url,
            'id': u.not_null,
            'region': 'RegionOne',
            'publicURL': u.valid_url,
            'internalURL': u.valid_url
        }
        expected = {
            'volume': [endpoint_check],
            'identity': [endpoint_check]
        }
        actual = self.keystone_v2.service_catalog.get_endpoints()

        ret = u.validate_svc_catalog_endpoint_data(expected, actual)
        if ret:
            amulet.raise_status(amulet.FAIL, msg=ret)

    def test_140_keystone_endpoint(self):
        """Verify the keystone endpoint data."""
        u.log.debug('Checking keystone api endpoint data...')
        endpoints = self.keystone_v2.endpoints.list()
        admin_port = '35357'
        internal_port = public_port = '5000'
        expected = {
            'id': u.not_null,
            'region': 'RegionOne',
            'adminurl': u.valid_url,
            'internalurl': u.valid_url,
            'publicurl': u.valid_url,
            'service_id': u.not_null
        }
        ret = u.validate_endpoint_data(endpoints, admin_port, internal_port,
                                       public_port, expected)
        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='keystone endpoint: {}'.format(ret))

    def test_142_cinder_endpoint(self):
        """Verify the cinder endpoint data."""
        u.log.debug('Checking cinder endpoint...')
        endpoints = self.keystone_v2.endpoints.list()
        admin_port = internal_port = public_port = '8776'
        expected = {
            'id': u.not_null,
            'region': 'RegionOne',
            'adminurl': u.valid_url,
            'internalurl': u.valid_url,
            'publicurl': u.valid_url,
            'service_id': u.not_null
        }

        ret = u.validate_endpoint_data(endpoints, admin_port, internal_port,
                                       public_port, expected)
        if ret:
            amulet.raise_status(amulet.FAIL,
                                msg='cinder endpoint: {}'.format(ret))

    def test_200_keystone_mysql_shared_db_relation(self):
        """Verify the keystone shared-db relation data"""
        u.log.debug('Checking keystone to mysql db relation data...')
        unit = self.keystone_sentry
        relation = ['shared-db', 'mysql:shared-db']
        expected = {
            'username': 'keystone',
            'private-address': u.valid_ip,
            'hostname': u.valid_ip,
            'database': 'keystone'
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('keystone shared-db', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_201_mysql_keystone_shared_db_relation(self):
        """Verify the mysql shared-db relation data"""
        u.log.debug('Checking mysql to keystone db relation data...')
        unit = self.mysql_sentry
        relation = ['shared-db', 'keystone:shared-db']
        expected_data = {
            'private-address': u.valid_ip,
            'password': u.not_null,
            'db_host': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected_data)
        if ret:
            message = u.relation_error('mysql shared-db', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_202_keystone_cinder_identity_service_relation(self):
        """Verify the keystone identity-service relation data"""
        u.log.debug('Checking keystone to cinder id relation data...')
        unit = self.keystone_sentry
        relation = ['identity-service', 'cinder:identity-service']
        expected = {
            'service_protocol': 'http',
            'service_tenant': 'services',
            'admin_token': 'ubuntutesting',
            'service_password': u.not_null,
            'service_port': '5000',
            'auth_port': '35357',
            'auth_protocol': 'http',
            'private-address': u.valid_ip,
            'auth_host': u.valid_ip,
            'service_username': 'cinder_cinderv2',
            'service_tenant_id': u.not_null,
            'service_host': u.valid_ip
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('keystone identity-service', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_203_cinder_keystone_identity_service_relation(self):
        """Verify the cinder identity-service relation data"""
        u.log.debug('Checking cinder to keystone id relation data...')
        unit = self.cinder_sentry
        relation = ['identity-service', 'keystone:identity-service']
        expected = {
            'cinder_service': 'cinder',
            'cinder_region': 'RegionOne',
            'cinder_public_url': u.valid_url,
            'cinder_internal_url': u.valid_url,
            'cinder_admin_url': u.valid_url,
            'cinderv2_service': 'cinderv2',
            'cinderv2_region': 'RegionOne',
            'cinderv2_public_url': u.valid_url,
            'cinderv2_internal_url': u.valid_url,
            'cinderv2_admin_url': u.valid_url,
            'private-address': u.valid_ip,
        }
        ret = u.validate_relation_data(unit, relation, expected)
        if ret:
            message = u.relation_error('cinder identity-service', ret)
            amulet.raise_status(amulet.FAIL, msg=message)

    def test_300_keystone_default_config(self):
        """Verify the data in the keystone config file,
           comparing some of the variables vs relation data."""
        u.log.debug('Checking keystone config file...')
        unit = self.keystone_sentry
        conf = '/etc/keystone/keystone.conf'
        ks_ci_rel = unit.relation('identity-service',
                                  'cinder:identity-service')
        my_ks_rel = self.mysql_sentry.relation('shared-db',
                                               'keystone:shared-db')
        db_uri = "mysql://{}:{}@{}/{}".format('keystone',
                                              my_ks_rel['password'],
                                              my_ks_rel['db_host'],
                                              'keystone')
        expected = {
            'DEFAULT': {
                'debug': 'False',
                'verbose': 'False',
                'admin_token': ks_ci_rel['admin_token'],
                'use_syslog': 'False',
                'log_config': '/etc/keystone/logging.conf',
                'public_endpoint': u.valid_url,  # get specific
                'admin_endpoint': u.valid_url,  # get specific
            },
            'extra_headers': {
                'Distribution': 'Ubuntu'
            },
            'database': {
                'connection': db_uri,
                'idle_timeout': '200'
            }
        }

        if self._get_openstack_release() >= self.trusty_kilo:
            # Kilo and later
            expected['eventlet_server'] = {
                'admin_bind_host': '0.0.0.0',
                'public_bind_host': '0.0.0.0',
                'admin_port': '35347',
                'public_port': '4990',
            }
        else:
            # Juno and earlier
            expected['DEFAULT'].update({
                'admin_port': '35347',
                'public_port': '4990',
                'bind_host': '0.0.0.0',
            })

        for section, pairs in expected.iteritems():
            ret = u.validate_config_data(unit, conf, section, pairs)
            if ret:
                message = "keystone config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_302_keystone_logging_config(self):
        """Verify the data in the keystone logging config file"""
        u.log.debug('Checking keystone config file...')
        unit = self.keystone_sentry
        conf = '/etc/keystone/logging.conf'
        expected = {
            'logger_root': {
                'level': 'WARNING',
                'handlers': 'file,production',
            },
            'handlers': {
                'keys': 'production,file,devel'
            },
            'handler_file': {
                'level': 'DEBUG',
                'args': "('/var/log/keystone/keystone.log', 'a')"
            }
        }

        for section, pairs in expected.iteritems():
            ret = u.validate_config_data(unit, conf, section, pairs)
            if ret:
                message = "keystone logging config error: {}".format(ret)
                amulet.raise_status(amulet.FAIL, msg=message)

    def test_900_keystone_restart_on_config_change(self):
        """Verify that the specified services are restarted when the config
           is changed."""
        sentry = self.keystone_sentry
        juju_service = 'keystone'

        # Expected default and alternate values
        set_default = {'use-syslog': 'False'}
        set_alternate = {'use-syslog': 'True'}

        # Services which are expected to restart upon config change,
        # and corresponding config files affected by the change
        if self.is_liberty_or_newer():
            services = {'apache2': '/etc/keystone/keystone.conf'}
        else:
            services = {'keystone-all': '/etc/keystone/keystone.conf'}
        # Make config change, check for service restarts
        u.log.debug('Making config change on {}...'.format(juju_service))
        mtime = u.get_sentry_time(sentry)
        self.d.configure(juju_service, set_alternate)

        sleep_time = 30
        for s, conf_file in services.iteritems():
            u.log.debug("Checking that service restarted: {}".format(s))
            if not u.validate_service_config_changed(sentry, mtime, s,
                                                     conf_file,
                                                     sleep_time=sleep_time):

                self.d.configure(juju_service, set_default)
                msg = "service {} didn't restart after config change".format(s)
                amulet.raise_status(amulet.FAIL, msg=msg)

        self.d.configure(juju_service, set_default)

        u.log.debug('OK')

    def test_901_pause_resume(self):
        """Test pause and resume actions."""
        self._assert_services(should_run=True)
        action_id = u.run_action(self.keystone_sentry, "pause")
        assert u.wait_on_action(action_id), "Pause action failed."

        self._assert_services(should_run=False)

        action_id = u.run_action(self.keystone_sentry, "resume")
        assert u.wait_on_action(action_id), "Resume action failed"
        self._assert_services(should_run=True)
