#!/usr/bin/env python3
"""Chromium contract test: third provider schema, desired vs applied and log replay."""
import argparse,json,re
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect

USER={'id':'control-admin','username':'control-admin','email':'control@example.test','is_active':True,'is_admin':True}
ENGINE={'id':'vm-test','slug':'vm-test','display_name':'VM de teste','adapter_type':'third-provider','status':'paused','health':'unknown','health_reason':None,'is_system':False,'version':1,'budget':{'limit_usd':10,'min_remaining_usd':0,'soft_pct':80,'period_tz':'UTC','period_anchor_day':1},'credentials':{},'credentials_updated_at':None,'config':{},'features':{},'gpu_budget':[],'config_error':None,'updated_at':'2026-10-06T12:00:00'}
CAP={'type':'third-provider','title':'Third VM provider','managed':False,'execution_mode':'queue','create_connection':True,'requires_budget':True,'fields':[{'name':'desired_replicas','label':'Instâncias desejadas','type':'number','min':0,'max':5},{'name':'max_replicas','label':'Máximo de instâncias','type':'number','min':0,'max':5}],'provider_fields':[{'name':'zone','label':'Zona do provider','type':'text'}],'credential_fields':[],'features':['transcription'],'actions':[{'type':'scale','supported':True,'enabled':True,'reason':None},{'type':'warmup','supported':True,'enabled':False,'reason':'NOT_SUPPORTED'}],'hosts':[]}
MODEL={'id':'vm-whisper','title':'VM Whisper','feature':'transcription','adapters':['third-provider'],'approved':True,'footprint_gb':3,'model':'approved/whisper'}


def check(browser,url,mobile=False,expect_insecure=False,api_url='http://localhost:8080'):
    context=browser.new_context(viewport={'width':390 if mobile else 1280,'height':850})
    auth=json.dumps({'state':{'user':USER,'token':'browser-control-fixture'},'version':0})
    context.add_init_script("localStorage.setItem('auth-storage',"+json.dumps(auth)+");")
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    state={'profile':None,'operations':[],'executions':0,'recoveries':0,'sequence':0,'saved':None,'keys':[]}
    def api(route):
        parsed=urlparse(route.request.url);path=parsed.path.removeprefix('/api');method=route.request.method
        def reply(value,status=200):route.fulfill(status=status,json=value,headers={'access-control-allow-origin':'*'})
        if method=='OPTIONS':return route.fulfill(status=204,headers={'access-control-allow-origin':'*','access-control-allow-headers':'*','access-control-allow-methods':'*'})
        if path=='/auth/me':return reply(USER)
        if path=='/admin/engines/vm-test':return reply(ENGINE)
        if path=='/admin/engines/vm-test/capabilities':return reply(CAP)
        if path=='/admin/engine-adapters':return reply([{'type':'third-provider','gpu_options':'instance selected by provider'}])
        if path=='/admin/model-profiles':return reply([MODEL])
        if path=='/admin/engines/vm-test/runtime-profile':
            if method=='PUT':
                body=route.request.post_data_json;state['saved']=body;state['profile']={'id':'profile','feature':'transcription','revision':1,'profile':body['profile'],'applied_at':None};ENGINE['version']=2
            return reply(state['profile'])
        if path=='/admin/engines/vm-test/runtime-status':return reply({'desired':{'transcription':state['profile']} if state['profile'] else {},'applied':[],'resources':[]})
        if path=='/admin/engines/vm-test/operation-plans':return reply({'plan_id':'plan','plan_hash':'hash','type':'scale','estimated_max_usd':'0.1','destructive':False,'resources':['vm:allocation'],'stages':['allocating','booting'],'effects':['allocate'],'expires_at':'2026-10-06T12:05:00','profile_revision':1})
        if path=='/admin/engines/vm-test/operations':
            state['keys'].append(route.request.headers.get('idempotency-key'))
            if len(state['keys'])==1:return reply({'detail':'Falha temporária; tente novamente'},503)
            state['executions']+=1;op={'operation_id':'operation','state':'running','stage':'booting','can_cancel':True,'last_seq':2,'error':None,'result':{},'created_at':'2026-10-06T12:00:00','reserved_usd':'0.1','actual_usd':None,'cost_confirmed':False};state['operations']=[op];return reply(op,202)
        if path=='/admin/engine-operations':return reply({'operations':state['operations']})
        if path=='/admin/engine-operations/operation':return reply(state['operations'][0])
        if path=='/admin/engine-operations/operation/events':
            after=int(parse_qs(parsed.query).get('after',['0'])[0]);ev=[{'seq':1,'type':'stage.changed','stage':'allocating','payload':{'message':'VM solicitada'},'at':'2026-10-06T12:00:00'},{'seq':2,'type':'log','stage':'booting','payload':{'message':'Worker iniciou'},'at':'2026-10-06T12:00:01'}]
            if state['recoveries']:
                ev.append({'seq':3,'type':'stage.changed','stage':'verifying','payload':{'message':'Estado reconciliado'},'at':'2026-10-06T12:00:02'})
            return reply({'events':[e for e in ev if e['seq']>after],'next':len(ev),'has_more':False,'state':state['operations'][0]['state']})
        if path=='/admin/engine-operations/operation/cancel':state['operations'][0]['state']='cancelled';state['operations'][0]['can_cancel']=False;return reply(state['operations'][0])
        if path=='/admin/engine-operations/operation/recover':
            state['recoveries']+=1
            state['operations'][0].update(state='running',stage='verifying',can_recover=False)
            return reply(state['operations'][0],202)
        return reply({},404)
    page.route('**/admin/**',api);page.route('**/auth/me',api)
    # API routes only, so the actual Next page and its assets remain unmocked.
    page.unroute('**/admin/**',api)
    page.route('http://localhost:8080/**',api);page.route('http://127.0.0.1:8080/**',api)
    page.route(api_url.rstrip('/')+'/**',api)
    page.goto(url+'/admin/engines/vm-test')
    if expect_insecure:
        assert page.evaluate('isSecureContext') is False
        assert page.evaluate('typeof crypto.randomUUID')=='undefined'
        assert page.evaluate('typeof crypto.getRandomValues')=='function'
    expect(page.get_by_text(re.compile('docker compose')).first).to_be_visible()
    page.get_by_role('tab',name='Configuração',exact=True).click()
    page.get_by_label('Zona do provider').fill('us-test-1')
    page.get_by_label('Instâncias desejadas').fill('2')
    page.get_by_label('Máximo de instâncias').fill('2')
    page.get_by_role('button',name='Salvar configuração desejada').click()
    expect(page.get_by_text('Salvar cria uma revisão.',exact=False)).to_be_visible()
    assert state['saved']['profile']['provider_settings']=={'zone':'us-test-1'}
    assert ENGINE['features']=={},'saving desired must not change applied'
    page.get_by_role('tab',name='Visão geral').click()
    expect(page.get_by_role('button',name='Aquecer',exact=True)).to_be_disabled()
    page.get_by_role('button',name='Aplicar escala',exact=True).click()
    expect(page.get_by_role('region',name='Revisar operação')).to_be_visible()
    page.get_by_role('button',name='Confirmar e executar').click()
    expect(page.get_by_role('alert').filter(has_text='Falha temporária')).to_be_visible()
    page.get_by_role('button',name='Confirmar e executar').click()
    expect(page.get_by_role('log')).to_contain_text('Worker iniciou')
    assert len(state['keys'])==2 and state['keys'][0]==state['keys'][1], 'retry must preserve idempotency'
    assert re.fullmatch('[0-9a-f]{32}',state['keys'][0]), 'operation needs a random key on HTTP too'
    page.reload()
    expect(page.get_by_role('log')).to_contain_text('VM solicitada')
    assert state['executions']==1,'reopening must not execute again'
    page.get_by_role('button',name='Solicitar cancelamento').click()
    expect(page.get_by_text('booting · cancelled',exact=True)).to_be_visible()
    state['operations'][0].update(state='needs_attention',can_recover=True)
    page.reload()
    page.get_by_role('button',name='Reconciliar estado sem repetir operação').click()
    expect(page.get_by_role('log')).to_contain_text('Estado reconciliado')
    assert state['recoveries']==1 and state['executions']==1
    assert not errors,errors
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile overflow'
    context.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:3107');parser.add_argument('--expect-insecure',action='store_true');parser.add_argument('--api-url',default='http://localhost:8080');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
        check(browser,args.url,expect_insecure=args.expect_insecure,api_url=args.api_url);check(browser,args.url,True,args.expect_insecure,args.api_url);browser.close()
    print('Chromium desktop/mobile: schema, desired, review, execution, replay, cancel and recovery passed')
