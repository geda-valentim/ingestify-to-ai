#!/usr/bin/env python3
"""Exercise Full's grouped navigation, multiple instances, geometry and terminal diagnostics.

--fixture accepts a private local snapshot with {job_id,name,status,result}.
Only browser API responses are replaced; the app renders its real components.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

spec = importlib.util.spec_from_file_location('vision_fixture', Path(__file__).with_name('vision-analysis-browser.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)


def check(browser, url, snapshot, viewport, status, baseline=False):
    job = snapshot['job_id']; result = copy.deepcopy(snapshot['result']); image = result['image']
    image['analysis_status'] = status
    if status == 'failed':
        for step in image['results']:
            step.update(status='failed', text='', regions=[], lines=[], reason_code='inference_failed')
    context = browser.new_context(viewport=viewport, permissions=['clipboard-read', 'clipboard-write'])
    auth = json.dumps({'state': {'user': fixture.USER, 'token': 'synthetic-design-token'}, 'version': 0})
    context.add_init_script("localStorage.setItem('auth-storage', " + json.dumps(auth) + ');')
    page = context.new_page(); errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    def intercept(route):
        request=route.request
        if request.resource_type not in ('fetch','xhr') or request.headers.get('rsc') == '1': return route.continue_()
        if request.method=='OPTIONS': return route.fulfill(status=204,headers=fixture.CORS)
        path=urlparse(request.url).path.removeprefix('/api'); value=None
        if path=='/auth/me': value=fixture.USER
        elif path=='/projects': value={'projects':[fixture.PROJECT]}
        elif path==f'/jobs/{job}': value={'job_id':job,'type':'main','kind':'image','status':status,'progress':100,'name':snapshot['name'],'tags':[], 'created_at':snapshot['created_at'], 'project':fixture.PROJECT,
            'image_analysis':{'status':status,'steps_total':len(image['results']),'steps_completed':len(image['results']),'calls_started':image['calls_started'],'cancel_requested':status=='cancelled'}}
        elif path==f'/jobs/{job}/result': value={'job_id':job,'type':'main','status':status,'result':result}
        if value is None: return route.fulfill(status=404,json={'detail':'Fixture unavailable'},headers=fixture.CORS)
        route.fulfill(json=value,headers=fixture.CORS)
    page.route('**/*',intercept)
    try:
        page.goto(url.rstrip('/')+'/jobs/'+job)
        expect(page.get_by_role('heading',name='Full Analysis',exact=True)).to_be_visible()
        if baseline:
            page.screenshot(path=f'/tmp/image-full-before-{viewport["width"]}.png',full_page=True)
            return
        navigation=page.get_by_role('navigation',name='Cobertura das tarefas')
        expect(navigation.locator('button')).to_have_count(15)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal page overflow'
        if viewport['width']<1024:
            assert page.get_by_role('heading',name='Full Analysis',exact=True).bounding_box()['y'] < viewport['height']
        select=page.get_by_label('Camada da análise')
        def family(task):
            item=next(f for f in image['coverage']['families'] if f['task']==task); label=item['label']
            if viewport['width']<1024: select.select_option(task)
            else: navigation.get_by_role('button',name=f"{label} {item['succeeded']}/{item['instances']}",exact=True).click()
            expect(page.get_by_role('region',name='Resultado selecionado').get_by_role('heading',name=label,exact=True)).to_be_visible()
        for item in image['coverage']['families']:
            family(item['task'])
            steps=[step for step in image['results'] if step['task']==item['task']]
            if len(steps)>1:
                buttons=page.get_by_role('group',name='Resultados da família').get_by_role('button')
                expect(buttons).to_have_count(len(steps))
                for i,step in enumerate(steps):
                    buttons.nth(i).click();expect(buttons.nth(i)).to_have_attribute('aria-pressed','true')
                    page.get_by_role('tab',name='Detalhes',exact=True).click()
                    page.get_by_text('Entrada da tarefa',exact=True).click()
                    if step['input'].get('text_input'):
                        expect(page.locator('details[open] pre').filter(has_text=step['input']['text_input'])).to_be_visible()
                    page.get_by_role('tab',name='Resultado',exact=True).click()
        if status=='completed':
            family('<OD>')
            count=len(next(s for s in image['results'] if s['task']=='<OD>')['regions'])
            expect(page.locator('svg[aria-label="Regiões detectadas"] g')).to_have_count(count)
            page.get_by_role('button',name='Ocultar regiões',exact=True).click()
            expect(page.locator('svg[aria-label="Regiões detectadas"]')).to_have_count(0)
            page.get_by_role('button',name='Mostrar regiões',exact=True).click()
            page.get_by_role('tab',name=f'Regiões ({count})',exact=True).click()
            region=page.get_by_role('tabpanel').get_by_role('button').first
            region.click();expect(region).to_have_attribute('aria-pressed','true')
            page.get_by_role('button',name='Ampliar imagem',exact=True).click()
            dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
            dialog.get_by_label('Zoom da imagem').fill('2')
            expect(dialog.get_by_text('200%',exact=True)).to_be_visible()
            page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
            page.get_by_role('tab',name='Resultado',exact=True).click()
        else:
            family('<CAPTION>')
            expect(page.get_by_text('Esta etapa não tem conteúdo disponível.',exact=True)).to_be_visible() if status=='failed' else None
            assert not page.get_by_role('heading',name='Processing failed',exact=True).count()
        page.reload();expect(page.get_by_role('heading',name='Full Analysis',exact=True)).to_be_visible()
        page.get_by_role('heading',name='Full Analysis',exact=True).evaluate("el => { const panel=el.closest('.overflow-y-auto'); if (panel) panel.scrollTop=0; window.scrollTo(0,0); }")
        page.screenshot(path=f'/tmp/image-full-design-{viewport["width"]}-{status}.png',full_page=True)
        assert not errors, errors
        print(f'PASS Full design: {len(image["results"])} instances, {viewport["width"]}px, {status}',flush=True)
    except Exception:
        print('Failure:',status,viewport['width'],page.url,errors,page.locator('body').inner_text()[:1800],flush=True)
        page.screenshot(path='/tmp/image-full-design-failure.png',full_page=True)
        raise
    finally: context.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:3107');parser.add_argument('--fixture',required=True);parser.add_argument('--baseline',action='store_true');parser.add_argument('--chromium');args=parser.parse_args()
    snapshot=json.loads(Path(args.fixture).read_text())
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
        try:
            for viewport in ({'width':1440,'height':1100},{'width':390,'height':844}):
                for status in (['completed'] if args.baseline else ['completed','failed','cancelled']): check(browser,args.url,snapshot,viewport,status,args.baseline)
        finally: browser.close()
