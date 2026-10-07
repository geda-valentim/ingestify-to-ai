#!/usr/bin/env python3
"""Full upload/retry key, inputs, partial result layers, exports and reload."""
import argparse
import base64
from email.parser import BytesParser
from email.policy import default
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

spec = importlib.util.spec_from_file_location('native_vision', Path(__file__).with_name('vision-analysis-browser.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
USER, PROJECT, JOB, PNG, CORS = fixture.USER, fixture.PROJECT, fixture.JOB, fixture.PNG, fixture.CORS


def check(browser, url, viewport):
    context = browser.new_context(viewport=viewport)
    auth = json.dumps({'state': {'user':USER, 'token':'synthetic-full-token'}, 'version':0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ');')
    page = context.new_page(); captured=[]; errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    steps = [{'step_id':str(i), 'task':t['task'], 'input':{}, 'status':'succeeded', 'text':t['label'],
              'output':{'labels':[t['label']]}, 'regions':[], 'lines':[], 'attempts':1} for i,t in enumerate(fixture.TASKS)]
    next(s for s in steps if s['task']=='<OD>')['regions']=[{'label':'FULL_OBJECT', 'bbox':[0,0,1,1], 'polygons':[]}]
    next(s for s in steps if s['task']=='<REFERRING_EXPRESSION_SEGMENTATION>')['regions']=[{'label':'FULL_MASK', 'polygons':[[0,0,1,0,1,1,0,1]]}]
    steps[-1].update(status='failed', text='', reason_code='inference_failed')
    image = {'operation':'full_analysis', 'schema_version':'image-full-result-v1', 'profile':'image-full-v1',
        'analysis_status':'partial', 'task':'full', 'description':'FULL_DESCRIPTION', 'text':'FULL_DESCRIPTION',
        'image_base64':base64.b64encode(PNG).decode(), 'image_mime_type':'image/png', 'width':1,'height':1,
        'model':{'model_id':'fixture','revision':'fixture','device':'cpu','dtype':'float32'},'duration_ms':500,
        'calls_started':15,'results':steps,'resolved_inputs':{'queries':[],'regions':[],'omitted_candidates':[]},
        'coverage':{'task_families_total':15,'task_families_completed':14,'instances_planned':15,'instances_completed':14,
            'families':[{'task':s['task'],'label':fixture.TASKS[i]['label'],'completed':s['status']=='succeeded','instances':1,'succeeded':int(s['status']=='succeeded')} for i,s in enumerate(steps)]}}
    def intercept(route):
        req=route.request
        if req.resource_type not in ('fetch','xhr') or req.headers.get('rsc') == '1': return route.continue_()
        if req.method=='OPTIONS': return route.fulfill(status=204,headers=CORS)
        path=urlparse(req.url).path.removeprefix('/api'); value=None
        if path=='/auth/me':value=USER
        elif path=='/projects':value={'projects':[PROJECT]}
        elif path=='/datalakes':value={'connections':[]}
        elif path=='/images/capabilities':value={'enabled':True,'dependencies_installed':True,'model_downloaded':True,
            'max_image_size_mb':10,'tasks':fixture.TASKS,'analysis_modes':['single','full'],
            'caption_tasks':['<CAPTION>'], 'default_caption_task':'<CAPTION>',
            'generation_schema':fixture.GENERATION,'generation_defaults':{'max_new_tokens':1024,'num_beams':3}}
        elif path=='/images/analyze/upload':
            message=BytesParser(policy=default).parsebytes(b'Content-Type: '+req.headers['content-type'].encode()+b'\r\n\r\n'+req.post_data_buffer)
            parts={p.get_param('name',header='content-disposition'):p.get_payload(decode=True) for p in message.iter_parts()}
            assert parts['mode']==b'full' and parts['wait']==b'false' and parts['file']==PNG
            assert not {'task','region','generation','text_input'} & set(parts)
            assert req.headers['idempotency-key']
            captured.append((req.headers['idempotency-key'],json.loads(parts['full_options'])))
            if len(captured)<3:return route.abort('failed')
            return route.fulfill(status=202,json={'job_id':JOB,'status':'queued','project':PROJECT},headers=CORS)
        elif path==f'/jobs/{JOB}':value={'job_id':JOB,'type':'main','kind':'image','status':'partial','progress':100,'name':'image.png','tags':[],'created_at':'2026-10-06T00:00:00','project':PROJECT,
            'configuration':{'operation':'image','options':{'mode':'full'}},'image_analysis':{'status':'partial','steps_total':15,'steps_completed':15,'calls_started':15,'cancel_requested':False}}
        elif path==f'/jobs/{JOB}/result':value={'job_id':JOB,'type':'main','status':'partial','completed_at':'2026-10-06T00:00:00','result':{'markdown':'FULL_DESCRIPTION','metadata':{'format':'image/png','size_bytes':len(PNG)},'image':image}}
        elif path==f'/jobs/{JOB}/pages':value={'job_id':JOB,'total_pages':0,'pages_completed':0,'pages_failed':0,'pages':[]}
        if value is None:return route.fulfill(status=404,json={'detail':'Fixture unavailable'},headers=CORS)
        route.fulfill(json=value,headers=CORS)
    page.route('**/*',intercept)
    try:
        page.goto(url.rstrip('/')+'/convert?project_id='+PROJECT['id'])
        page.locator('input[type="file"]').set_input_files({'name':'image.png','mimeType':'image/png','buffer':PNG})
        page.get_by_label('Processamento da imagem').select_option('full')
        submit=page.get_by_role('button',name='Processar imagem',exact=True)
        expect(submit).to_be_enabled();submit.click()
        page.wait_for_function('true');expect(submit).to_be_enabled();submit.click()
        expect(submit).to_be_enabled()
        assert len(captured)==2 and captured[0][0]==captured[1][0], captured
        page.get_by_text('Consultas e região de interesse (opcional)',exact=True).click()
        queries=page.get_by_label('Objetos ou expressões, uma por linha (até 3)')
        queries.fill('one\ntwo\nthree\nfour');expect(submit).to_be_disabled()
        queries.fill('a red car');expect(submit).to_be_enabled();submit.click()
        page.wait_for_url('**/jobs/'+JOB,timeout=45000)
        assert captured[-1][0]!=captured[0][0]
        assert captured[-1][1]['queries']==['a red car']
        expect(page.get_by_role('heading',name='Full Analysis',exact=True)).to_be_visible()
        expect(page.get_by_text('FULL_DESCRIPTION',exact=True)).to_be_visible()
        layer=page.get_by_label('Camada da análise');expect(layer.locator('option')).to_have_count(15)
        def select_family(task):
            if viewport['width'] < 1024:
                layer.select_option(task)
            else:
                family=next(t for t in fixture.TASKS if t['task']==task)
                coverage=next(item for item in image['coverage']['families'] if item['task']==task)
                page.get_by_role('navigation',name='Cobertura das tarefas').get_by_role('button',name=f"{family['label']} {coverage['succeeded']}/{coverage['instances']}",exact=True).click()
        for task in ('<OD>','<REFERRING_EXPRESSION_SEGMENTATION>'):
            select_family(task)
            expect(page.locator('svg[aria-label="Regiões detectadas"] g')).to_have_count(1)
        select_family(steps[-1]['task'])
        expect(page.get_by_text('Não foi possível concluir esta tarefa.',exact=True)).to_be_visible()
        page.get_by_role('tab',name='Detalhes',exact=True).click()
        expect(page.get_by_text('inference_failed',exact=True)).to_be_visible()
        with page.expect_download() as info:page.get_by_role('button',name='Download JSON',exact=True).click()
        assert info.value.suggested_filename.endswith('.full.json')
        with page.expect_download() as info:page.get_by_role('button',name='Download Markdown',exact=True).click()
        target=Path('/tmp/image-full-browser-report.md');info.value.save_as(target)
        assert 'inference_failed' in target.read_text()
        page.reload();expect(page.get_by_role('heading',name='Full Analysis',exact=True)).to_be_visible()
        assert not errors, errors
        page.screenshot(path='/tmp/image-full-'+str(viewport['width'])+'.png',full_page=True)
        print(f"PASS full upload/retry/configuration/partial/layers/downloads/F5 viewport {viewport['width']}",flush=True)
    except Exception:
        print('Browser failure:', page.url, errors, page.locator('body').inner_text()[:1200], flush=True)
        page.screenshot(path='/tmp/image-full-browser-failure.png', full_page=True)
        raise
    finally:context.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:3107');parser.add_argument('--chromium');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        try:
            for viewport in ({'width':1440,'height':1100},{'width':390,'height':844}):check(browser,args.url,viewport)
        finally:browser.close()
