#!/usr/bin/env python3
"""Chromium contract tests for execution profile publication, binding and access.

All API requests are fulfilled locally. These checks never provision a provider,
call a live API, or mutate the application's database. Start an isolated frontend
and pass its URL; NEXT_PUBLIC_API_URL must match --api-url.
"""
import argparse
import copy
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

CHROMIUM = '/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome'
READ = ['engines.read', 'execution_profiles.read', 'engine_operations.read']
ROLES = {
    'observer': READ,
    'profile_editor': ['execution_profiles.read', 'execution_profiles.create',
                       'execution_profiles.update', 'execution_profiles.publish',
                       'execution_profiles.archive'],
    'runtime_configurator': READ + ['engine_runtime.bind'],
    'engine_operator': READ + ['engine_operations.plan', 'engine_operations.execute.scale'],
    'access_admin': ['access.grants.manage'],
    'connection_manager': READ + ['engine_connections.credentials.manage'],
}
USER = {'id': 'fixture-admin', 'username': 'fixture-admin', 'email': 'admin@example.test',
        'is_active': True, 'is_admin': True, 'engine_access_enabled': True,
        'permissions': sorted(set(sum(ROLES.values(), [])))}
ENGINE = {'id': 'vm-test', 'slug': 'vm-test', 'display_name': 'VM de teste',
          'adapter_type': 'third-provider', 'status': 'paused', 'health': 'unknown',
          'health_reason': None, 'is_system': False, 'version': 3,
          'budget': {'limit_usd': 10, 'min_remaining_usd': 0, 'soft_pct': 80,
                     'period_tz': 'UTC', 'period_anchor_day': 1},
          'credentials': {}, 'credentials_updated_at': None, 'config': {},
          'features': {}, 'gpu_budget': [], 'config_error': None,
          'updated_at': '2026-10-06T12:00:00'}
CAP = {'type': 'third-provider', 'title': 'Third VM provider', 'managed': False,
       'execution_mode': 'queue', 'create_connection': True, 'requires_budget': True,
       'fields': [{'name': 'desired_replicas', 'label': 'Instâncias desejadas', 'type': 'number', 'min': 0, 'max': 5},
                  {'name': 'max_replicas', 'label': 'Máximo de instâncias', 'type': 'number', 'min': 0, 'max': 5}],
       'provider_fields': [{'name': 'zone', 'label': 'Zona do provider', 'type': 'text'}],
       'credential_fields': [], 'features': ['transcription'],
       'actions': [{'type': 'scale', 'supported': True, 'enabled': True, 'reason': None}], 'hosts': []}
MODEL = {'id': 'vm-whisper', 'title': 'VM Whisper', 'feature': 'transcription',
         'adapters': ['third-provider'], 'approved': True, 'footprint_gb': 3,
         'model': 'approved/whisper'}
RUNTIME = {'adapter_version': 1, 'schema_version': 1,
           'binding': {'workers': 2, 'executions_per_worker': 1, 'cpu': 1},
           'model_profile_id': MODEL['id'], 'desired_replicas': 2, 'max_replicas': 2,
           'min_ready_replicas': 0, 'idle_timeout_seconds': 60, 'memory_mb': 1024,
           'warmup_mode': 'on_start', 'warm_until': None,
           'provider_settings': {'zone': 'us-test-1'}}
CONSTRAINTS = {'engine_ids': ['vm-test'], 'profile_ids': None,
               'adapters': ['third-provider'], 'features': ['transcription'],
               'environments': ['development'], 'host_ids': None,
               'gpu_uuids': None, 'model_ids': ['vm-whisper'],
               'max_replicas': 2, 'max_concurrency': 1, 'max_cpu': 1,
               'max_memory_mb': 1024, 'max_warm_seconds': 300, 'max_usd': '0.10'}


def published_profile():
    return {'id': 'profile-one', 'name': 'VM publicado', 'description': 'Transcrição de teste',
            'adapter_type': 'third-provider', 'feature': 'transcription',
            'environment': 'development', 'status': 'published', 'version': 1,
            'latest_published_revision_id': 'revision-one',
            'permissions': ['read', 'update', 'publish', 'archive'], 'bindings': [],
            'revisions': [{'id': 'revision-one', 'revision': 1,
                           'settings': copy.deepcopy(RUNTIME), 'warm_for_seconds': 300,
                           'content_hash': 'fixture-hash', 'model_fingerprint': 'fixture-model',
                           'published_at': '2026-10-06T12:00:00'}]}


class Fixture:
    def __init__(self, browser, api_url, user=None, mobile=False, seed=False):
        self.user = copy.deepcopy(user or USER)
        self.context = browser.new_context(viewport={'width': 390 if mobile else 1280, 'height': 850},
                                           timezone_id='America/Sao_Paulo')
        auth = json.dumps({'state': {'user': self.user, 'token': 'execution-profile-fixture'}, 'version': 0})
        self.context.add_init_script("localStorage.setItem('auth-storage'," + json.dumps(auth) + ');')
        self.page = self.context.new_page()
        self.page.set_default_navigation_timeout(60_000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.engine = copy.deepcopy(ENGINE)
        self.descriptors = [copy.deepcopy(CAP)]
        self.models = [copy.deepcopy(MODEL)]
        self.reads = []
        self.strict_feature = False
        self.profiles = [published_profile()] if seed else []
        if not self.user['is_admin']:
            for profile in self.profiles:
                profile['permissions'] = [action for action in ('read', 'update', 'publish', 'archive')
                                          if f'execution_profiles.{action}' in self.user['permissions']]
        self.desired = None
        self.policies = []
        self.grants = []
        self.attributes = []
        self.resources = [{'key': 'vm:allocation', 'owner_engine_id': ENGINE['id'],
                           'version': 0, 'consumers': [], 'qualified': False}]
        self.writes = []
        self.unhandled = []
        self.bind_conflict = False
        self.context.route(api_url.rstrip('/') + '/**', self.dispatch)

    def dispatch(self, route):
        try:
            self.api(route)
        except AssertionError as error:
            # A fixture contract failure must reach the browser and fail the
            # assertion, rather than leaving the intercepted request pending.
            self.errors.append(str(error))
            route.fulfill(status=500, json={'detail': str(error)},
                          headers={'access-control-allow-origin': '*'})

    def api(self, route):
        parsed = urlparse(route.request.url)
        path = parsed.path.removeprefix('/api')
        query = parse_qs(parsed.query)
        method = route.request.method

        def reply(value, status=200):
            route.fulfill(status=status, json=value,
                          headers={'access-control-allow-origin': '*'})

        if method == 'OPTIONS':
            return route.fulfill(status=204, headers={'access-control-allow-origin': '*',
                                'access-control-allow-headers': '*', 'access-control-allow-methods': '*'})
        if method == 'GET': self.reads.append((path, query, self.user['id']))
        if path == '/auth/login': return reply({'access_token': 'fixture-observer-token', 'token_type': 'bearer'})
        body = route.request.post_data_json if method in ('POST', 'PUT') else None
        if method != 'GET':
            self.writes.append((path, copy.deepcopy(body)))
        if path == '/auth/me': return reply(self.user)
        if path == '/admin/access/me':
            return reply({'enabled': True, 'bootstrap': self.user['is_admin'], 'permissions': self.user['permissions']})
        if path == '/admin/engine-control-adapters': return reply(self.descriptors)
        if path == '/admin/engine-adapters':
            return reply([{'type': d['type'], 'gpu_options': 'Provider-managed GPU'} for d in self.descriptors])
        if path == '/admin/model-profiles': return reply(self.models)
        if path == '/admin/execution-profile-hosts': return reply([])
        if path == '/admin/engines': return reply([self.engine])
        if path == '/admin/engines/vm-test': return reply(self.engine)
        if path == '/admin/engines/vm-test/capabilities':
            cap = copy.deepcopy(next(d for d in self.descriptors if d['type'] == self.engine['adapter_type']))
            if self.strict_feature and query.get('feature'):
                assert query['feature'][0] in cap['features'], f'Unscoped capability feature {query}'
            if not self.user['is_admin']:
                for action in cap['actions']:
                    if f"engine_operations.execute.{action['type']}" not in self.user['permissions']:
                        action.update(enabled=False, reason='ACCESS_DENIED')
            return reply(cap)
        if path == '/admin/engines/vm-test/runtime-profile':
            if self.strict_feature:
                cap = next(d for d in self.descriptors if d['type'] == self.engine['adapter_type'])
                assert query.get('feature', [''])[0] in cap['features'], f'Unscoped runtime feature {query}'
            return reply(self.desired)
        if path == '/admin/engines/vm-test/credentials':
            assert self.user['is_admin'] or 'engine_connections.credentials.manage' in self.user['permissions']
            assert body['version'] == self.engine['version']
            self.engine['version'] += 1
            return reply(self.engine)
        if path == '/admin/engines/vm-test/runtime-status':
            return reply({'desired': {'transcription': self.desired} if self.desired else {},
                          'applied': [], 'resources': []})
        if path == '/admin/engine-operations': return reply({'operations': []})
        if path == '/admin/engines/vm-test/runtime-profile/bind':
            if self.bind_conflict: return reply({'detail': {'code': 'VERSION_CONFLICT'}}, 409)
            p = next(p for p in self.profiles if any(r['id'] == body['revision_id'] for r in p['revisions']))
            r = next(r for r in p['revisions'] if r['id'] == body['revision_id'])
            assert r['published_at'], 'browser submitted a draft revision for binding'
            assert body['version'] == self.engine['version']
            runtime = copy.deepcopy(r['settings'])
            runtime['warm_until'] = '2026-10-06T12:05:00Z'
            self.desired = {'id': 'desired-one', 'feature': body['feature'], 'revision': 1,
                            'profile': runtime, 'source_profile_revision_id': r['id'],
                            'source_hash': r['content_hash'], 'applied_at': None}
            self.engine['version'] += 1
            return reply(self.desired)
        if path == '/admin/execution-profiles':
            if method == 'GET': return reply(self.profiles)
            p = {k: body[k] for k in ('name', 'description', 'adapter_type', 'feature', 'environment')}
            p.update(id=f'profile-{len(self.profiles)+1}', status='draft', version=0,
                     latest_published_revision_id=None, permissions=['read', 'update', 'publish', 'archive'], bindings=[])
            p['revisions'] = [self.revision(p, body, 1)]
            self.profiles.append(p)
            return reply(p, 201)
        if path.startswith('/admin/execution-profiles/'):
            parts = path.split('/')
            p = next(p for p in self.profiles if p['id'] == parts[3])
            if method == 'GET': return reply(p)
            assert body['version'] == p['version'], 'stale profile write'
            if parts[-1] == 'publish':
                r = next(r for r in p['revisions'] if r['id'] == body['revision_id'])
                r['published_at'] = '2026-10-06T12:00:00'
                p.update(status='published', latest_published_revision_id=r['id'])
            elif parts[-1] == 'revisions':
                p['revisions'].insert(0, self.revision(p, body, len(p['revisions'])+1))
            else: raise AssertionError(f'Unexpected profile mutation {path}')
            p['version'] += 1
            return reply(p)
        if path == '/admin/access/roles': return reply(ROLES)
        if path == '/admin/access/subjects': return reply([self.user])
        if path == '/admin/access/policies':
            if method == 'POST':
                self.policies.append({'id': 'policy-one', 'name': body['name'], 'version': 0,
                                      'revisions': [{'id': 'policy-r1', 'revision': 1, 'constraints': body['constraints']}]})
                return reply(self.policies[-1], 201)
            return reply(self.policies)
        if path == '/admin/access/policies/policy-one/revisions':
            p = self.policies[0]
            assert body['version'] == p['version']
            p['version'] += 1
            p['revisions'].insert(0, {'id': 'policy-r2', 'revision': 2, 'constraints': body['constraints']})
            return reply(p)
        if path == '/admin/access/grants':
            if method == 'POST':
                g = copy.deepcopy(body)
                g.update(id='grant-one' if not self.grants else 'grant-two',
                         version=0, parent_id=None, revoked_at=None)
                g['expires_at'] = g['expires_at'].removesuffix('Z')
                self.grants.append(g)
                return reply(g, 201)
            return reply(self.grants)
        if path == '/admin/access/grants/grant-one/revoke':
            assert body['version'] == self.grants[0]['version']
            self.grants[0].update(revoked_at='2026-10-06T12:00:00', version=1)
            return reply(self.grants[0])
        if path == '/admin/access/engine-attributes': return reply(self.attributes)
        if path == '/admin/access/engine-attributes/vm-test':
            self.attributes = [{'engine_id': 'vm-test', 'environment': body['environment'], 'version': body['version']+1}]
            return reply(self.attributes[0])
        if path == '/admin/access/resources':
            if method == 'PUT':
                r = self.resources[0]
                assert body['version'] == r['version']
                r.update(body)
                r['version'] += 1
                return reply(r)
            return reply(self.resources)
        self.unhandled.append((method, path))
        return reply({'detail': 'Mock route unavailable'}, 404)

    @staticmethod
    def revision(p, body, n):
        runtime = body['settings']
        assert max(runtime['desired_replicas'], runtime['min_ready_replicas']) <= runtime['max_replicas']
        assert runtime['binding']['workers'] == runtime['max_replicas']
        assert runtime['warm_until'] is None, 'library templates must store a relative duration'
        return {'id': f"{p['id']}-r{n}", 'revision': n, 'settings': copy.deepcopy(body['settings']),
                'warm_for_seconds': body['warm_for_seconds'], 'content_hash': f'content-r{n}',
                'model_fingerprint': 'fixture-model', 'published_at': None}

    def finish(self):
        assert not self.errors, self.errors
        assert not self.unhandled, self.unhandled
        assert self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal viewport overflow'
        self.context.close()


def library_check(browser, url, api_url, mobile):
    f = Fixture(browser, api_url, mobile=mobile)
    p = f.page
    p.goto(url + '/admin/execution-profiles')
    expect(p.get_by_role('heading', name='Perfis de execução', exact=True)).to_be_visible()
    p.get_by_label('Nome', exact=True).fill('Perfil VM')
    p.get_by_label('Descrição', exact=True).fill('Transcrição com provider externo')
    p.get_by_label('Provider', exact=True).select_option('third-provider')
    p.get_by_label('Modelo aprovado').select_option('vm-whisper')
    p.get_by_label('Zona do provider').fill('us-test-1')
    p.get_by_label('Instâncias desejadas').fill('2')
    p.get_by_label('Máximo de instâncias').fill('2')
    p.get_by_label('Duração aquecida (segundos)').fill('300')
    p.get_by_role('button', name='Salvar rascunho', exact=True).click()
    expect(p.get_by_text('Revisão 1 · Rascunho', exact=True)).to_be_visible()
    saved = f.writes[0][1]
    assert saved['settings']['provider_settings'] == {'zone': 'us-test-1'}
    assert saved['settings']['warm_until'] is None
    assert saved['settings']['binding']['workers'] == saved['settings']['max_replicas'] == 2
    assert saved['warm_for_seconds'] == 300
    assert all('/operations' not in path and 'operation-plans' not in path for path, _ in f.writes)
    p.get_by_role('button', name='Publicar revisão 1', exact=True).click()
    expect(p.get_by_text('Revisão 1 · Publicada', exact=True)).to_be_visible()
    assert f.writes[-1][1] == {'version': 0, 'revision_id': 'profile-1-r1'}
    published = copy.deepcopy(f.profiles[0]['revisions'][0])
    p.get_by_role('button', name='Nova revisão', exact=True).click()
    expect(p.get_by_text('Criar revisão imutável', exact=True)).to_be_visible()
    p.get_by_label('Instâncias desejadas').fill('3')
    p.get_by_label('Máximo de instâncias').fill('3')
    p.get_by_role('button', name='Salvar nova revisão', exact=True).click()
    expect(p.get_by_text('Revisão 2 · Rascunho', exact=True)).to_be_visible()
    expect(p.get_by_text('Revisão 1 · Publicada', exact=True)).to_be_visible()
    assert f.profiles[0]['revisions'][1] == published, 'new draft changed prior immutable publication'
    assert f.profiles[0]['latest_published_revision_id'] == published['id']
    p.get_by_role('button', name='Clonar', exact=True).click()
    expect(p.get_by_label('Nome', exact=True)).to_have_value('Perfil VM (cópia)')
    p.get_by_role('button', name='Salvar rascunho', exact=True).click()
    expect(p.get_by_text('Revisão 1 · Rascunho', exact=True)).to_be_visible()
    assert len(f.profiles) == 2 and f.profiles[1]['latest_published_revision_id'] is None
    assert f.profiles[1]['revisions'][0]['settings']['desired_replicas'] == 3
    f.finish()
    print(f'Library {"mobile" if mobile else "desktop"}: draft, explicit publication, immutable revision and clone passed')


def binding_check(browser, url, api_url, mobile):
    user = {**USER, 'is_admin': False, 'permissions': ROLES['runtime_configurator']}
    f = Fixture(browser, api_url, user=user, mobile=mobile, seed=True)
    f.profiles[0]['revisions'].insert(0, {**copy.deepcopy(f.profiles[0]['revisions'][0]),
                                          'id': 'draft-two', 'revision': 2, 'published_at': None})
    p = f.page
    p.goto(url + '/admin/engines/vm-test')
    p.get_by_role('tab', name='Configuração', exact=True).click()
    expect(p.get_by_role('heading', name='Perfil de execução publicado')).to_be_visible()
    expect(p.get_by_role('button', name='Salvar configuração desejada')).to_have_count(0)
    p.get_by_label('Escolher perfil', exact=True).select_option('profile-one')
    p.get_by_label('Revisão publicada', exact=True).select_option('revision-one')
    expect(p.locator('#execution-revision option')).to_have_count(2)
    expect(p.get_by_role('table')).to_contain_text('300s a partir da vinculação')
    p.get_by_role('button', name='Vincular ao desejado', exact=True).click()
    expect(p.get_by_text('Origem: revision-one · desejado r1', exact=True)).to_be_visible()
    assert f.writes == [('/admin/engines/vm-test/runtime-profile/bind',
                         {'feature': 'transcription', 'version': 3, 'revision_id': 'revision-one'})]
    assert f.engine['features'] == {} and f.desired['applied_at'] is None
    assert f.desired['profile']['warm_until'] == '2026-10-06T12:05:00Z'
    expect(p.get_by_role('link', name='Criar perfil', exact=True)).to_have_count(0)
    f.bind_conflict = True
    p.get_by_role('button', name='Vincular ao desejado', exact=True).click()
    expect(p.get_by_role('alert').filter(has_text='VERSION_CONFLICT')).to_be_visible()
    p.wait_for_timeout(750)
    assert len(f.writes) == 2, 'version conflict retried a binding without explicit user action'
    f.finish()
    print(f'Binding {"mobile" if mobile else "desktop"}: published-only, desired-only and no conflict retry passed')


def navigation_check(browser, url, api_url):
    expected = {'observer': ['Home', 'Engines', 'Perfis de execução'],
                'profile_editor': ['Home', 'Perfis de execução'],
                'runtime_configurator': ['Home', 'Engines', 'Perfis de execução'],
                'access_admin': ['Home', 'Acesso']}
    for role, tabs in expected.items():
        user = {**USER, 'is_admin': False, 'permissions': ROLES[role]}
        f = Fixture(browser, api_url, user=user, seed=True)
        p = f.page
        p.goto(url + ('/admin/access' if role == 'access_admin' else '/admin/execution-profiles'))
        nav = p.get_by_role('navigation', name='Compute sections')
        expect(nav).to_be_visible()
        assert nav.get_by_role('link').all_text_contents() == tabs
        if role != 'access_admin':
            expect(p.get_by_role('button', name='Novo perfil', exact=True)).to_have_count(1 if role == 'profile_editor' else 0)
            p.get_by_role('button', name='VM publicado third-provider', exact=False).click()
            expect(p.get_by_text('Revisão 1 · Publicada', exact=True)).to_be_visible()
            expect(p.get_by_role('button', name='Nova revisão', exact=True)).to_have_count(1 if role == 'profile_editor' else 0)
            expect(p.get_by_role('button', name='Clonar', exact=True)).to_have_count(1 if role == 'profile_editor' else 0)
            expect(p.get_by_role('button', name='Arquivar', exact=True)).to_have_count(1 if role == 'profile_editor' else 0)
        if role == 'observer':
            p.goto(url + '/admin/engines/vm-test')
            expect(p.get_by_text('VM de teste', exact=True)).to_be_visible()
            expect(p.get_by_role('button', name='Aplicar escala', exact=True)).to_be_disabled()
            p.get_by_role('tab', name='Configuração', exact=True).click()
            expect(p.get_by_text('Solicite ao configurador de runtime a vinculação de um perfil publicado.', exact=True)).to_be_visible()
            expect(p.get_by_role('button', name='Vincular ao desejado', exact=True)).to_have_count(0)
            expect(p.get_by_role('button', name='Salvar configuração desejada', exact=True)).to_have_count(0)
        p.goto(url + '/admin/gpus')
        expect(p.get_by_role('navigation', name='Compute sections')).to_have_count(0)
        f.finish()
    print('Delegated navigation: observer, editor, configurator and access_admin passed')


def access_check(browser, url, api_url, mobile):
    f = Fixture(browser, api_url, mobile=mobile)
    p = f.page
    p.goto(url + '/admin/access')
    p.get_by_label('Nome da política', exact=True).fill('Dev VM')
    for key in ('engine_ids', 'adapters', 'features', 'environments', 'model_ids'):
        p.locator('#scope-' + key).fill(', '.join(CONSTRAINTS[key]))
    for key in ('max_replicas', 'max_concurrency', 'max_cpu', 'max_memory_mb', 'max_warm_seconds', 'max_usd'):
        p.locator('#scope-' + key).fill(str(CONSTRAINTS[key]))
    p.get_by_role('button', name='Criar política', exact=True).click()
    expect(p.get_by_text('Dev VM', exact=True)).to_be_visible()
    assert f.writes[-1] == ('/admin/access/policies', {'name': 'Dev VM', 'constraints': CONSTRAINTS})
    p.get_by_label('ID do usuário', exact=True).fill('operator-user')
    p.get_by_label('Papel', exact=True).select_option('engine_operator')
    p.get_by_label('Revisão da política', exact=True).select_option('policy-r1')
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    p.get_by_label('Válido até', exact=False).fill(expiry.strftime('%Y-%m-%dT%H:%M'))
    p.get_by_role('button', name='Conceder papel', exact=True).click()
    expect(p.get_by_role('button', name='Revogar', exact=True)).to_be_visible()
    grant = f.writes[-1][1]
    assert grant['user_id'] == 'operator-user' and grant['policy_revision_id'] == 'policy-r1'
    assert grant['permissions'] == ROLES['engine_operator'] and grant['delegation'] is None
    assert grant['expires_at'].endswith('Z')
    expected_expiry = datetime.fromisoformat(expiry.strftime('%Y-%m-%dT%H:%M')).replace(
        tzinfo=timezone(timedelta(hours=-3))).astimezone(timezone.utc)
    assert grant['expires_at'] == expected_expiry.strftime('%Y-%m-%dT%H:%M:00.000Z')
    p.get_by_role('button', name='Nova revisão', exact=True).click()
    p.locator('#scope-max_replicas').fill('1')
    p.get_by_role('button', name='Salvar nova revisão', exact=True).click()
    expect(p.get_by_text('r2, r1 · policy-one', exact=True)).to_be_visible()
    assert f.grants[0]['policy_revision_id'] == 'policy-r1', 'policy revision migrated existing grant'
    p.get_by_role('button', name='Revogar', exact=True).click()
    expect(p.get_by_role('button', name='Revogar', exact=True)).to_have_count(0)
    assert f.writes[-1] == ('/admin/access/grants/grant-one/revoke', {'version': 0})
    p.get_by_label('ID do usuário', exact=True).fill('access-user')
    p.get_by_label('Papel', exact=True).select_option('access_admin')
    p.get_by_label('Revisão da política', exact=True).select_option('policy-r2')
    p.get_by_label('Definir envelope de delegação', exact=False).check()
    p.get_by_label('engine_operations.execute.scale', exact=True).check()
    for key in ('engine_ids', 'adapters', 'features', 'environments', 'model_ids'):
        p.locator('#delegation-' + key).fill(', '.join(CONSTRAINTS[key]))
    p.get_by_label('Validade máxima concedível (s)', exact=True).fill('600')
    p.get_by_role('button', name='Conceder papel', exact=True).click()
    expect(p.get_by_text('Usuário access-user · política policy-r2', exact=True)).to_be_visible()
    grant = f.writes[-1][1]
    assert grant['permissions'] == ['access.grants.manage'], 'access_admin acquired execution rights from envelope'
    assert grant['delegation']['permissions'] == ['engine_operations.execute.scale']
    assert grant['delegation']['max_grant_seconds'] == 600
    assert grant['delegation']['constraints']['engine_ids'] == ['vm-test']
    p.get_by_label('Ambiente VM de teste', exact=True).select_option('development')
    expect(p.get_by_label('Ambiente VM de teste', exact=True)).to_have_value('development')
    assert f.writes[-1] == ('/admin/access/engine-attributes/vm-test', {'environment': 'development', 'version': 0})
    p.get_by_role('button', name='Adicionar consumidor', exact=True).click()
    p.get_by_label('Engine consumidor 1 vm:allocation', exact=True).fill('vm-test')
    p.get_by_label('Feature consumidor 1 vm:allocation', exact=True).fill('transcription')
    p.get_by_label('Confirmei todos os consumidores deste recurso', exact=True).check()
    p.get_by_role('button', name='Salvar escopo', exact=True).click()
    expect(p.get_by_label('Confirmei todos os consumidores deste recurso', exact=True)).to_be_checked()
    assert f.writes[-1] == ('/admin/access/resources', {'key': 'vm:allocation', 'version': 0,
                                                     'consumers': [{'engine_id': 'vm-test', 'feature': 'transcription'}],
                                                     'qualified': True})
    f.finish()
    print(f'Access {"mobile" if mobile else "desktop"}: constraints, pinned grant, revision, revocation, classification and scope passed')


def token_renewal_check(browser, url, api_url):
    f = Fixture(browser, api_url)
    p = f.page
    p.goto(url + '/admin/execution-profiles')
    expect(p.get_by_role('button', name='Novo perfil', exact=True)).to_be_visible()
    p.get_by_label('Nome', exact=True).fill('Rascunho durante renovação')
    p.get_by_label('Descrição', exact=True).fill('Estado deve sobreviver ao refresh')
    p.get_by_label('Modelo aprovado').select_option('vm-whisper')
    p.get_by_label('Zona do provider').fill('zona-editada')
    p.get_by_label('Instâncias desejadas').fill('2')
    p.evaluate("""() => {
        window.__renewalInput = document.querySelector('#profile-name');
        window.__renewalInput.dataset.mountMarker = 'original-session-form';
        window.__renewalUnmounts = 0;
        window.__renewalObserver = new MutationObserver((records) => {
            for (const record of records) {
                for (const node of record.removedNodes) {
                    if (node === window.__renewalInput || node.contains?.(window.__renewalInput)) {
                        window.__renewalUnmounts++;
                    }
                }
            }
        });
        window.__renewalObserver.observe(document.body, {childList: true, subtree: true});
    }""")
    initial_library_reads = len([path for path, _, _ in f.reads if path == '/admin/execution-profiles'])
    for token in ('renewed-fixture-token-1', 'renewed-fixture-token-2'):
        auth = json.dumps({'state': {'user': f.user, 'token': token}, 'version': 0})
        # This is the same storage event that SessionHeartbeat handles when
        # another tab renews the JWT; it calls Zustand persist.rehydrate().
        with p.expect_response(lambda response: '/auth/me' in response.url
                               and response.request.headers.get('authorization') == 'Bearer ' + token):
            p.evaluate("""auth => {
                const oldValue = localStorage.getItem('auth-storage');
                localStorage.setItem('auth-storage', auth);
                dispatchEvent(new StorageEvent('storage', {
                    key: 'auth-storage', oldValue, newValue: auth, storageArea: localStorage,
                }));
            }""", auth)
        expect(p.get_by_label('Nome', exact=True)).to_have_value('Rascunho durante renovação')
        expect(p.get_by_label('Descrição', exact=True)).to_have_value('Estado deve sobreviver ao refresh')
        expect(p.get_by_label('Modelo aprovado')).to_have_value('vm-whisper')
        expect(p.get_by_label('Zona do provider')).to_have_value('zona-editada')
        expect(p.get_by_label('Instâncias desejadas')).to_have_value('2')
        assert p.evaluate("window.__renewalInput === document.querySelector('#profile-name') && window.__renewalInput.isConnected"), 'token renewal remounted the form'
        assert p.evaluate("window.__renewalInput.dataset.mountMarker") == 'original-session-form'
        assert p.evaluate('window.__renewalUnmounts') == 0, 'token renewal removed the session subtree'
    assert len([path for path, _, _ in f.reads if path == '/admin/execution-profiles']) == initial_library_reads, 'same-session renewal discarded the query cache'
    p.evaluate('window.__renewalObserver.disconnect()')
    f.finish()
    print('Token renewal: two storage rehydrates preserve form state, DOM mount identity and session query cache passed')


def session_isolation_check(browser, url, api_url):
    f = Fixture(browser, api_url, seed=True)
    p = f.page
    p.goto(url + '/admin/execution-profiles')
    expect(p.get_by_role('button', name='Novo perfil', exact=True)).to_be_visible()
    expect(p.get_by_role('button', name='VM publicado third-provider', exact=False)).to_be_visible()
    p.get_by_role('button', name='Account menu for fixture-admin', exact=True).click()
    p.get_by_role('menuitem', name='Logout', exact=True).click()
    expect(p.get_by_label('Username or Email', exact=True)).to_be_visible()
    p.evaluate("history.replaceState(null, '', '/login?next=/admin/execution-profiles')")
    f.user = {**USER, 'id': 'fixture-observer', 'username': 'fixture-observer',
              'is_admin': False, 'permissions': ROLES['observer']}
    f.profiles = [published_profile()]
    f.profiles[0].update(id='observer-only-profile', name='Perfil exclusivo B', permissions=['read'])
    p.get_by_label('Username or Email', exact=True).fill('fixture-observer')
    p.get_by_label('Password', exact=True).fill('fixture-password')
    p.get_by_role('button', name='Sign In', exact=True).click()
    expect(p.get_by_role('heading', name='Perfis de execução', exact=True)).to_be_visible()
    expect(p.get_by_role('button', name='Perfil exclusivo B third-provider', exact=False)).to_be_visible()
    expect(p.get_by_role('button', name='VM publicado third-provider', exact=False)).to_have_count(0)
    expect(p.get_by_role('button', name='Novo perfil', exact=True)).to_have_count(0)
    nav = p.get_by_role('navigation', name='Compute sections')
    assert nav.get_by_role('link').all_text_contents() == ['Home', 'Engines', 'Perfis de execução']
    assert any(path == '/admin/access/me' and who == 'fixture-observer' for path, _, who in f.reads)
    assert any(path == '/admin/execution-profiles' and who == 'fixture-observer' for path, _, who in f.reads)
    f.finish()
    print('Same-tab session: actual logout/login refreshes cache, bootstrap and permissions without reloading passed')


def limited_adapter_check(browser, url, api_url):
    user = {**USER, 'is_admin': False, 'permissions': ROLES['profile_editor']}
    f = Fixture(browser, api_url, user=user)
    f.descriptors = [{**copy.deepcopy(CAP), 'type': 'modal', 'title': 'Modal', 'features': ['transcription']}]
    f.models = [{**MODEL, 'id': 'modal-whisper', 'adapters': ['modal']}]
    p = f.page
    p.goto(url + '/admin/execution-profiles')
    expect(p.get_by_label('Provider', exact=True)).to_have_value('modal')
    expect(p.get_by_label('Feature', exact=True)).to_have_value('transcription')
    p.get_by_label('Nome', exact=True).fill('Modal limitado')
    p.get_by_label('Modelo aprovado').select_option('modal-whisper')
    p.get_by_role('button', name='Salvar rascunho', exact=True).click()
    expect(p.get_by_text('Revisão 1 · Rascunho', exact=True)).to_be_visible()
    assert f.writes[-1][1]['adapter_type'] == 'modal'
    f.finish()
    print('Modal-only editor: provider normalization and valid draft passed')


def provider_feature_check(browser, url, api_url):
    f = Fixture(browser, api_url)
    f.descriptors = [{**copy.deepcopy(CAP), 'type': 'local', 'title': 'Local', 'features': ['vision']},
                     {**copy.deepcopy(CAP), 'type': 'modal', 'title': 'Modal', 'features': ['transcription']}]
    f.models = [{**MODEL, 'id': 'local-vision', 'adapters': ['local'], 'feature': 'vision'},
                {**MODEL, 'id': 'modal-whisper', 'adapters': ['modal']}]
    p = f.page
    p.goto(url + '/admin/execution-profiles')
    expect(p.get_by_label('Provider', exact=True)).to_have_value('local')
    expect(p.get_by_label('Feature', exact=True)).to_have_value('vision')
    p.get_by_label('Modelo aprovado').select_option('local-vision')
    p.get_by_label('Provider', exact=True).select_option('modal')
    expect(p.get_by_label('Feature', exact=True)).to_have_value('transcription')
    expect(p.get_by_label('Modelo aprovado')).not_to_have_value('local-vision')
    expect(p.get_by_label('Modelo aprovado').locator('option[value="local-vision"]')).to_have_count(0)
    p.get_by_label('Nome', exact=True).fill('Modal após vision')
    p.get_by_label('Modelo aprovado').select_option('modal-whisper')
    p.get_by_role('button', name='Salvar rascunho', exact=True).click()
    expect(p.get_by_text('Revisão 1 · Rascunho', exact=True)).to_be_visible()
    assert f.writes[-1][1]['feature'] == 'transcription'
    assert f.writes[-1][1]['settings']['model_profile_id'] == 'modal-whisper'
    f.finish()
    print('Provider switch: Local vision to Modal transcription resets feature and model passed')


def vision_discovery_check(browser, url, api_url):
    user = {**USER, 'is_admin': False, 'permissions': ROLES['runtime_configurator']}
    f = Fixture(browser, api_url, user=user)
    f.descriptors[0]['features'] = ['vision']
    f.models[0]['feature'] = 'vision'
    f.strict_feature = True
    p = f.page
    p.goto(url + '/admin/engines/vm-test')
    expect(p.get_by_text('VM de teste', exact=True)).to_be_visible()
    p.get_by_role('tab', name='Configuração', exact=True).click()
    expect(p.locator('#control-feature')).to_have_value('vision')
    expect(p.get_by_role('heading', name='Perfil de execução publicado')).to_be_visible()
    assert any(path.endswith('/capabilities') and not q for path, q, _ in f.reads)
    assert any(path.endswith('/runtime-profile') and q.get('feature') == ['vision'] for path, q, _ in f.reads)
    f.finish()
    print('Empty vision-only engine: feature discovery and scoped runtime requests passed')


def connection_manager_check(browser, url, api_url):
    user = {**USER, 'is_admin': False, 'permissions': ROLES['connection_manager']}
    f = Fixture(browser, api_url, user=user)
    f.descriptors[0]['credential_fields'] = [{'name': 'token', 'label': 'Token do provider', 'type': 'secret'}]
    p = f.page
    p.goto(url + '/admin/engines/vm-test')
    p.get_by_role('tab', name='Configuração', exact=True).click()
    expect(p.get_by_label('Token do provider', exact=True)).to_be_visible()
    expect(p.get_by_role('button', name='Salvar orçamento', exact=True)).to_have_count(0)
    expect(p.get_by_role('button', name='Salvar configuração desejada', exact=True)).to_have_count(0)
    expect(p.get_by_role('button', name='Vincular ao desejado', exact=True)).to_have_count(0)
    p.get_by_label('Token do provider', exact=True).fill('fixture-provider-token')
    p.get_by_label('Sua senha para confirmar a troca', exact=True).fill('fixture-confirmation')
    p.get_by_role('button', name='Salvar credenciais', exact=True).click()
    expect(p.get_by_label('Token do provider', exact=True)).to_have_value('')
    assert f.writes == [('/admin/engines/vm-test/credentials',
                         {'version': 3, 'fields': {'token': 'fixture-provider-token'}, 'current_password': 'fixture-confirmation'})]
    f.finish()
    print('Connection manager: credential write with password, hidden budget/runtime writes passed')


if __name__ == '__main__':
    expect.set_options(timeout=10_000)
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:3119')
    parser.add_argument('--api-url', default='http://localhost:8080')
    parser.add_argument('--section', choices=('all', 'library', 'binding', 'access', 'navigation', 'targeted', 'session', 'vision', 'renewal'), default='all')
    parser.add_argument('--desktop-only', action='store_true')
    args = parser.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])
        for mobile in ((False,) if args.desktop_only else (False, True)):
            if args.section in ('all', 'library'):
                library_check(browser, args.url, args.api_url, mobile)
            if args.section in ('all', 'binding'):
                binding_check(browser, args.url, args.api_url, mobile)
            if args.section in ('all', 'access'):
                access_check(browser, args.url, args.api_url, mobile)
        if args.section in ('all', 'navigation'):
            navigation_check(browser, args.url, args.api_url)
        if args.section in ('all', 'targeted', 'session', 'renewal'):
            token_renewal_check(browser, args.url, args.api_url)
        if args.section in ('all', 'targeted', 'session'):
            session_isolation_check(browser, args.url, args.api_url)
        if args.section in ('all', 'targeted'):
            limited_adapter_check(browser, args.url, args.api_url)
            provider_feature_check(browser, args.url, args.api_url)
            connection_manager_check(browser, args.url, args.api_url)
        if args.section in ('all', 'targeted', 'vision'):
            vision_discovery_check(browser, args.url, args.api_url)
        browser.close()
    print('Execution profile Chromium contract checks passed; no live infrastructure was called')
