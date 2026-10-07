#!/usr/bin/env python3
"""Facial upload/profile, recovery, layers, partial results and exports on desktop/mobile."""
import argparse
import base64
import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

JOB = '11111111-2222-4333-8444-555555555555'
USER = {'id':'face-browser','username':'face-browser','email':'face@example.test','is_active':True,'created_at':'2026-10-06T00:00:00'}
PROJECT = {'id':'face-project','name':'Faces','archived':False,'folders':[]}
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
SCHEMA = json.loads((Path(__file__).resolve().parents[1]/'docs/doc2md_openapi.json').read_text())
TASKS = SCHEMA['components']['schemas']['ImageAnalyzeOptions']['properties']['task']['x-task-catalog']
GENERATION = SCHEMA['components']['schemas']['VisionGenerationOptions']
FACIAL = ['face_detection','face_movements','face_expression_classification']


def check(browser, url, viewport, operation, detection=False, unavailable=False, empty=False):
    context = browser.new_context(viewport=viewport)
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(json.dumps({'state':{'user':USER,'token':'synthetic-face-browser'},'version':0})) + ');')
    page = context.new_page(); captured=[]; errors=[]; persisted={}
    page.on('pageerror', lambda error: errors.append(str(error)))
    faces = [] if empty else [{'face_id':f'face-00{i+1}','bbox':[.1,.1,.8,.8],'bbox_normalized':[.1,.1,.8,.8],'detection_confidence':.95,
        'keypoints':[{'index':n,'x':.2,'y':.3} for n in range(6)],
        'movements':{'status':'not_applicable' if detection else 'succeeded','reason_code':'not_requested' if detection else None,
            'landmarks':[] if detection else [{'index':n,'x':.4,'y':.5} for n in range(478)],
            'blendshapes':[] if detection else [{'name':f'movement-{n}','score':n/100} for n in range(52)]},
        'expression':{'status':'not_applicable' if detection else 'succeeded' if i==0 else 'failed',
            'reason_code':'not_requested' if detection else None if i==0 else 'face_association_ambiguous',
            'decision':'inconclusive','label':None,'score':.45,'threshold':.5,'calibrated':False,
            'scores':[] if detection else [{'label':name,'score':.45 if n==0 else .55/7} for n,name in enumerate(['Neutral','Happiness','Sadness','Surprise','Fear','Disgust','Anger','Contempt'])]}} for i in range(2)]
    facial = {'detection':{'status':'succeeded','detected_count':0 if empty else 3,'selected_count':len(faces),'omitted_count':0 if empty else 1,'selection_limited':not empty},
        'faces':faces,'request':{'mode':'detection' if detection else 'expressions','max_faces':2,'min_expression_score':.5},
        'models':[{'provider':'mediapipe','model_id':'pinned-model','revision':'1','sha256':'fixture','runtime':'mediapipe','runtime_version':'1.1.0','license':'Apache-2.0'}],
        'coverage':{'task_families_total':1 if detection else 3,'task_families_completed':1 if detection else 2,
            'families':[{'task':task,'label':task,'completed':n<2,'reason_codes':[]} for n,task in enumerate(FACIAL[:1] if detection else FACIAL)]},
        'steps':[{'kind':'face','step_id':'detection','operation':'face_detection','status':'succeeded'}]+([] if detection else [{'kind':'face','step_id':'expression-2','operation':'face_expression_classification','face_id':'face-002','status':'failed','reason_code':'face_association_ambiguous'}])}
    native = [{'kind':'florence','step_id':f'native-{i}','task':task['task'],'input':{},'status':'succeeded','text':task['label'],'regions':[],'lines':[]} for i,task in enumerate(TASKS)]
    common={'width':1,'height':1,'image_base64':base64.b64encode(PNG).decode(),'image_mime_type':'image/png','duration_ms':100,'calls_started':20,'analysis_status':'completed' if detection or empty else 'partial','reason_code':None,'calls_by_provider':{'mediapipe':3,'emotiefflib':2}}
    image = {**common,**facial,'operation':'face_analysis','profile':'image-faces-v1','schema_version':'face-result-v1'} if operation=='faces' else {
        **common,'operation':'full_analysis','profile':'image-full-v2','schema_version':'image-full-result-v2','faces':facial,'models':[],
        'model':{'model_id':'Florence','revision':'pinned','device':'cpu','dtype':'float32'},'description':'Native preserved','text':'Native preserved','lines':[],
        'results':native+facial['steps'],'resolved_inputs':{'queries':[],'regions':[],'omitted_candidates':[]},
        'coverage':{'task_families_total':18,'task_families_completed':17,'instances_planned':20,'instances_completed':19,
            'families':[{'task':task['task'],'label':task['label'],'completed':True,'instances':1,'succeeded':1} for task in TASKS]+facial['coverage']['families']}}
    def intercept(route):
        req=route.request
        if req.resource_type not in ('fetch','xhr') or req.headers.get('rsc')=='1': return route.continue_()
        if req.method=='OPTIONS':return route.fulfill(status=204)
        path=urlparse(req.url).path.removeprefix('/api');value=None
        if path=='/auth/me':value=USER
        elif path=='/projects':value={'projects':[PROJECT]}
        elif path=='/datalakes':value={'connections':[]}
        elif path==f'/jobs/{JOB}/datalake':value={'destination':None}
        elif path=='/images/capabilities':value={'enabled':True,'dependencies_installed':True,'model_downloaded':True,'max_image_size_mb':10,'tasks':TASKS,
            'caption_tasks':['<CAPTION>'],'default_caption_task':'<CAPTION>','generation_schema':GENERATION,'generation_defaults':{'num_beams':3,'max_new_tokens':1024},
            'full_profiles':[{'profile':'image-full-v1','ready':True,'families':15,'max_calls':32,'max_faces':0},{'profile':'image-full-v2','ready':not unavailable,'families':18,'max_calls':54,'max_faces':5}]}
        elif path=='/images/faces/capabilities':
            assert req.headers.get('authorization')=='Bearer synthetic-face-browser'
            value={'enabled':True,'ready':not unavailable,'stages':{task:{'ready':not unavailable or task=='face_detection'} for task in FACIAL},'models':[],'defaults':{'max_faces':9 if captured else 5},'max_image_size_mb':10}
        elif path in ('/images/faces/upload','/images/analyze/upload'):
            msg=BytesParser(policy=default).parsebytes(b'Content-Type: '+req.headers['content-type'].encode()+b'\r\n\r\n'+req.post_data_buffer)
            parts={p.get_param('name',header='content-disposition'):p.get_payload(decode=True) for p in msg.iter_parts()}
            assert parts['wait']==b'false' and parts['file']==PNG and req.headers.get('idempotency-key')
            options=json.loads(parts['face_options' if operation=='faces' else 'full_options'])
            captured.append((req.headers['idempotency-key'],options))
            persisted.update({'operation':'face_analysis' if operation=='faces' else 'full_analysis','options':{'mode':operation, 'face_options' if operation=='faces' else 'full_options':options}})
            if len(captured)<3: return route.abort('failed')
            return route.fulfill(status=202,json={'job_id':JOB,'status':'queued','project':PROJECT})
        elif path==f'/jobs/{JOB}':value={'job_id':JOB,'type':'main','kind':'image','status':image['analysis_status'],'progress':100,'name':'image.png','created_at':'2026-10-06T00:00:00','tags':[],'project':PROJECT,'configuration':persisted,
            'image_analysis':{'status':image['analysis_status'],'steps_total':20,'steps_completed':20,'calls_started':20,'cancel_requested':False}}
        elif path==f'/jobs/{JOB}/result':value={'job_id':JOB,'type':'main','status':image['analysis_status'],'result':{'markdown':'Test facial report','metadata':{'format':'image/png','size_bytes':len(PNG)},'image':image}}
        if value is None: return route.fulfill(status=404,json={'detail':'Fixture unavailable'})
        route.fulfill(json=value)
    page.route('**/*',intercept)
    try:
        page.goto(url.rstrip('/')+'/convert?project_id='+PROJECT['id'])
        page.locator('input[type=file]').set_input_files({'name':'image.png','mimeType':'image/png','buffer':PNG})
        page.get_by_label('Processamento da imagem').select_option(operation)
        submit=page.get_by_role('button',name='Processar imagem',exact=True)
        if operation=='full':
            profile=page.get_by_label('Perfil do Full Analysis');expect(profile).to_have_value('image-full-v1' if unavailable else 'image-full-v2')
            profile.select_option('image-full-v2')
        if unavailable:
            expect(submit).to_be_disabled()
            if operation=='faces':
                page.get_by_label('Análise facial').select_option('detection');expect(submit).to_be_enabled()
            assert not captured
            print('PASS: missing models block expressions/v2; detection independent',flush=True);return
        if detection:page.get_by_label('Análise facial').select_option('detection')
        expect(submit).to_be_enabled();submit.click();expect(page.get_by_role('alert').filter(has_text='Conversion failed')).to_be_visible()
        expect(submit).to_be_enabled();submit.click();expect(submit).to_be_enabled()
        page.wait_for_function('true')
        assert len(captured)==2 and captured[0][0]==captured[1][0],captured
        page.get_by_label('Máximo de rostos').fill('2')
        expect(submit).to_be_enabled();submit.click();page.wait_for_url('**/jobs/'+JOB,timeout=45000)
        assert captured[-1][0]!=captured[0][0]
        options=captured[-1][1];assert (options if operation=='faces' else options['faces'])['max_faces']==2
        if operation=='full':
            assert options['profile']=='image-full-v2'
            expect(page.get_by_role('heading',name='Full Analysis · rostos e expressões')).to_be_visible()
            with page.expect_download() as info:page.get_by_role('button',name='Baixar Full JSON').click()
            target=Path('/tmp/face-full-browser.json');info.value.save_as(target);assert json.loads(target.read_text())['profile']=='image-full-v2'
            with page.expect_download() as info:page.get_by_role('button',name='Baixar Markdown',exact=True).click()
            target=Path('/tmp/face-full-browser.md');info.value.save_as(target);assert '17/18' in target.read_text() and 'face_association_ambiguous' in target.read_text()
        expect(page.get_by_role('heading',name='Rostos e expressões',exact=True)).to_be_visible()
        if empty:expect(page.get_by_text('Nenhum rosto detectado nesta imagem.',exact=True)).to_be_visible()
        else:
            expect(page.get_by_text('Limite aplicado:',exact=False)).to_be_visible()
            selection=page.get_by_label('Rosto selecionado');expect(selection.locator('option')).to_have_count(2)
            page.get_by_label('Keypoints',exact=True).check();expect(page.locator('svg[aria-label="Camadas faciais"] circle')).to_have_count(12)
            if not detection:
                page.get_by_label('Landmarks',exact=True).check();expect(page.locator('svg[aria-label="Camadas faciais"] circle')).to_have_count(490)
                expect(page.get_by_text('Inconclusiva: score abaixo do limiar',exact=True)).to_be_visible()
                selection.select_option('face-002');expect(page.get_by_text('Não foi possível associar esta análise ao rosto com segurança.',exact=True)).to_be_visible()
            with page.expect_download() as info:page.get_by_role('button',name='Baixar análise facial',exact=True).click()
            assert info.value.suggested_filename.endswith('.faces.json')
            with page.expect_download() as info:page.get_by_role('button',name='Baixar facial Markdown',exact=True).click()
            target=Path('/tmp/face-specific-browser.md');info.value.save_as(target);assert 'pinned-model' in target.read_text() and ('not_requested' if detection else 'face_association_ambiguous') in target.read_text()
        page.reload();expect(page.get_by_role('heading',name='Rostos e expressões',exact=True)).to_be_visible()
        page.get_by_text('Detalhes e organização',exact=True).click();page.get_by_text('Configuração solicitada',exact=True).click()
        expect(page.locator('pre').filter(has_text='"max_faces": 2').first).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),viewport
        assert not errors,errors
        print(f'PASS: {operation}, detection={detection}, empty={empty}, viewport={viewport["width"]}, retry key, layers, partial, exports, F5',flush=True)
    except Exception:
        print('Browser failure:', page.url, page.locator('body').inner_text()[:3000], errors, flush=True)
        page.screenshot(path='/data/tmp/ingestify/face-browser-failure.png', full_page=True)
        raise
    finally:context.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:3074');parser.add_argument('--chromium');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        try:
            for width in (1440,390):
                for operation in ('faces','full'):check(browser,args.url,{'width':width,'height':950},operation)
            check(browser,args.url,{'width':1440,'height':950},'faces',detection=True)
            check(browser,args.url,{'width':390,'height':950},'faces',empty=True)
            for operation in ('faces','full'):check(browser,args.url,{'width':1440,'height':950},operation,unavailable=True)
        finally:browser.close()
