"""Jobs workspace acceptance tests. Every API request is intercepted; no real mutations."""
import asyncio,json,os,re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.async_api import async_playwright,expect
URL=os.environ.get('LANDING_URL','http://127.0.0.1:3108').rstrip('/')
OUT=Path(os.environ.get('SCREENSHOT_DIR','/data/tmp/ingestify/jobs-preview'))
USER={'id':'preview-user','username':'Preview','email':'preview@example.invalid','is_admin':False}
LONG='enterprise-quarterly-report-financial-consolidation'

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome'))
  ctx=await browser.new_context(viewport={'width':1440,'height':1000})
  await ctx.add_init_script('localStorage.setItem("auth-storage", '+json.dumps(json.dumps({'state':{'user':USER,'token':'local-browser-preview'},'version':0}))+');')
  projects=[{'id':f'p{i}','name':['Research','Operations','Archive','Product','Sales','Design','Engineering'][i],'archived':False,'job_count':21 if i<2 else 0,'root_job_count':0,'folders':[{'id':f'f{i}','name':'Reports','job_count':21}]} for i in range(7)]
  jobs=[{'job_id':f'job-{i}','type':'main','name':f'Report {i:02d}','filename':f'report-{i}.pdf','status':['completed','processing','queued','failed','cancelled'][i%5],'kind':['document','transcription','image'][i%3],'progress':65 if i%5==1 else 100,'total_pages':12,'pages_completed':8,'file_size_bytes':524288,'created_at':'2026-10-06T10:00:00Z','tags':(['finance','quarterly',LONG,'approved','topic-extra'] if i==0 else ['finance' if i%2==0 else 'research',f'topic-{i:02d}']),'project':{'id':f'p{i%2}','name':projects[i%2]['name']},'folder':{'id':f'f{i%2}','name':'Reports'},'error':'The source could not be processed.' if i%5==3 else None} for i in range(42)]
  mode='ok';tag_fail=False;delete_fail=False;requests=[];errors=[]
  async def mock(route):
   nonlocal mode,tag_fail,delete_fail,jobs
   req=route.request;u=urlparse(req.url);path=u.path;qs=parse_qs(u.query);requests.append((req.method,path,qs,req.post_data))
   if path.endswith('/auth/me'):data=USER
   elif path.endswith('/jobs'):
    if mode=='error':return await route.fulfill(status=503,json={'detail':'Jobs temporarily unavailable'})
    items=jobs[:]
    for key in ['project_id','folder_id']:
     if qs.get(key):items=[j for j in items if j['project' if key=='project_id' else 'folder']['id']==qs[key][0]]
    if qs.get('q'):items=[j for j in items if qs['q'][0].lower() in j['name'].lower()]
    if qs.get('kind'):items=[j for j in items if j['kind']==qs['kind'][0]]
    for tag in qs.get('tag',[]):items=[j for j in items if tag in j['tags']]
    counts={state:sum(j['status']==state for j in items) for state in ['completed','processing','queued','failed','cancelled']};counts['all']=len(items)
    if qs.get('status'):items=[j for j in items if j['status']==qs['status'][0]]
    offset=int(qs.get('offset',['0'])[0]);limit=int(qs.get('limit',['20'])[0])
    data={'total':len(items),'counts':counts,'offset':offset,'limit':limit,'jobs':items[offset:offset+limit]}
   elif path.endswith('/jobs/move') or path.endswith('/location'):
    body=req.post_data_json;ids=body.get('job_ids',[path.split('/')[-2]])
    for job in jobs:
     if job['job_id'] in ids:
      dest=next(p for p in projects if p['id']==body['project_id']);job['project']={'id':dest['id'],'name':dest['name']};job['folder']=None
    data={'moved':len(ids)}
   elif re.search(r'/jobs/[^/]+/tags$',path):
    if tag_fail:return await route.fulfill(status=503,json={'detail':'Could not save test tags'})
    job=next(j for j in jobs if j['job_id']==path.split('/')[-2]);job['tags']=req.post_data_json['tags'];data={'tags':job['tags']}
   elif req.method=='DELETE' and '/jobs/' in path:
    if delete_fail:return await route.fulfill(status=503,json={'detail':'Could not delete test job'})
    jobs=[j for j in jobs if j['job_id']!=path.split('/')[-1]];return await route.fulfill(status=200,json={'message':'Job deleted'})
   elif path.endswith('/tags'):
    counts=Counter(t for j in jobs for t in j['tags']);data={'tags':[{'tag':t,'count':n} for t,n in counts.items()]}
   elif path.endswith('/projects'):data={'projects':projects,'limits':{'max_projects':100,'max_folders_per_project':100}}
   elif path.endswith('/search'):data={'query':qs.get('query',[''])[0],'total':1,'limit':100,'results':[{'job_id':'job-0','filename':'report-0.pdf','preview':'Quarterly report content for the selected search.'}]}
   else:data={}
   await route.fulfill(status=200,json=data)
  await ctx.route('**/api/**',mock)
  page=await ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
  async def goto(path='/jobs'):
   await page.goto(URL+path,wait_until='networkidle')
   await expect(page.get_by_role('heading',name='Jobs',exact=True)).to_be_visible()
  await goto()
  listing=page.get_by_role('list',name='Jobs',exact=True)
  await expect(listing.get_by_role('link',name='Report 00',exact=True)).to_be_visible()
  assert await listing.locator(':scope > li').count()==20
  assert not await page.get_by_label('Find a tag',exact=True).is_visible()
  first_tags=page.get_by_role('group',name='Tags for Report 00',exact=True)
  assert await first_tags.get_by_role('button').count()==3
  await first_tags.get_by_role('button',name='Show all 5 tags for Report 00').click()
  assert await first_tags.get_by_role('button').count()==6
  assert page.url.endswith('/jobs')
  await first_tags.get_by_role('button',name='Show fewer tags for Report 00').click()
  await page.get_by_role('button',name='Tags',exact=True).click()
  await page.get_by_label('Find a tag',exact=True).fill('topic-40')
  await page.get_by_role('group',name='Available tags').get_by_role('button',name=re.compile('topic-40')).click()
  await expect(page).to_have_url(re.compile('tag=topic-40'))
  await expect(listing.get_by_role('link',name='Report 40',exact=True)).to_be_visible()
  await page.get_by_role('button',name='Remove tag filter topic-40',exact=True).click()
  await expect(page).not_to_have_url(re.compile('tag='))
  await page.get_by_role('button',name='Close tag filters').click()
  await goto('/jobs?project_id=p0&folder_id=f0&tag=finance&status=completed')
  await page.get_by_role('button',name='Reset filters',exact=True).first.click()
  await expect(page).to_have_url(URL+'/jobs?project_id=p0&folder_id=f0')
  assert await page.get_by_role('link',name='New conversion',exact=True).get_attribute('href')=='/convert?project_id=p0&folder_id=f0'
  await page.get_by_label('Search jobs by name',exact=True).fill('Report')
  await page.get_by_label('File type',exact=True).select_option('document')
  await expect(page).to_have_url(re.compile('q=Report'))
  assert parse_qs(urlparse(page.url).query)['kind']==['document']
  assert parse_qs(urlparse(page.url).query)['project_id']==['p0']
  await page.get_by_role('group',name='Job status').get_by_role('button',name=re.compile('Cancelled')).click()
  await expect(page).to_have_url(re.compile('status=cancelled'))
  await page.go_back();await expect(page).not_to_have_url(re.compile('status=cancelled'))
  await page.go_forward();await expect(page).to_have_url(re.compile('status=cancelled'))
  await page.get_by_role('group',name='Search in').get_by_role('button',name='Content',exact=True).click()
  await expect(page.get_by_role('list',name='Content matches')).to_be_visible()
  assert not await page.get_by_role('navigation',name='Projects',exact=True).is_visible()
  assert not await page.get_by_role('group',name='Job status').is_visible()
  assert 'across all your projects' in await page.get_by_role('region',name='Job filters').inner_text()
  await page.get_by_role('group',name='Search in').get_by_role('button',name='Jobs',exact=True).click()
  assert parse_qs(urlparse(page.url).query)['status']==['cancelled']
  await goto()
  await page.get_by_role('button',name='Actions for Report 00',exact=True).click()
  await page.get_by_role('menuitem',name='Edit tags',exact=True).click()
  dialog=page.get_by_role('dialog',name='Edit tags',exact=True)
  await dialog.get_by_label('Tags',exact=True).fill('reviewed')
  # Saving also commits the pending input on blur without a second click.
  tag_fail=True;await dialog.get_by_role('button',name='Save tags',exact=True).click()
  await expect(dialog.get_by_role('alert')).to_contain_text('Could not save')
  tag_fail=False;await dialog.get_by_role('button',name='Save tags',exact=True).click()
  await expect(dialog).not_to_be_visible()
  assert 'reviewed' in jobs[0]['tags']
  await expect(page.get_by_role('button',name='Show all 6 tags for Report 00')).to_be_visible()
  if await page.get_by_role('checkbox',name='Select Report 00',exact=True).count():
   await page.get_by_role('checkbox',name='Select Report 00',exact=True).check()
   await expect(page.get_by_role('checkbox',name='Select all jobs on this page')).to_have_attribute('data-state','indeterminate')
   await page.get_by_role('checkbox',name='Select Report 01',exact=True).check()
   await page.get_by_role('button',name='Move selected',exact=True).click()
   move=page.get_by_role('dialog',name='Move 2 jobs',exact=True)
   await move.get_by_label('Destination project').select_option('p2')
   await move.get_by_role('button',name='Move',exact=True).click()
   await expect(move).not_to_be_visible()
   assert jobs[0]['project']['id']=='p2' and jobs[1]['project']['id']=='p2'
   assert 'reviewed' in jobs[0]['tags']
  await page.get_by_role('button',name='Actions for Report 00',exact=True).click()
  await page.get_by_role('menuitem',name='Delete job',exact=True).click()
  confirm=page.get_by_role('alertdialog');await confirm.get_by_role('button',name='Cancel',exact=True).click()
  assert not any(method=='DELETE' for method,*_ in requests)
  await page.get_by_role('button',name='Actions for Report 00',exact=True).click()
  await page.get_by_role('menuitem',name='Delete job',exact=True).click()
  delete_fail=True;await confirm.get_by_role('button',name='Delete',exact=True).click()
  await expect(page.get_by_text('Error deleting job',exact=True)).to_be_visible()
  await expect(confirm).to_be_visible()
  delete_fail=False;await confirm.get_by_role('button',name='Delete',exact=True).click()
  await expect(confirm).not_to_be_visible()
  await expect(listing.get_by_role('link',name='Report 00',exact=True)).not_to_be_visible()
  await page.get_by_role('button',name='Next page',exact=True).click()
  await expect(page).to_have_url(re.compile('page=2'))
  await expect(page.get_by_role('button',name='Page 2',exact=True)).to_have_attribute('aria-current','page')
  await goto('/jobs?page=999')
  await expect(page).to_have_url(URL+'/jobs?page=3')
  await goto('/jobs?page=NaN&status=invalid&kind=invalid')
  jobs_requests=[qs for method,path,qs,body in requests if path.endswith('/jobs')]
  assert all('NaN' not in qs.get('offset',[]) and qs.get('status')!=['invalid'] for qs in jobs_requests)
  await goto('/jobs?q=missing-file-xyz')
  await expect(page.get_by_text('No jobs match these filters',exact=True)).to_be_visible()
  mode='error';await goto()
  await expect(page.get_by_role('alert').filter(has_text='Could not load your jobs')).to_be_visible(timeout=15000)
  mode='ok';await page.get_by_role('button',name='Try again',exact=True).click()
  await expect(listing.get_by_role('link',name='Report 01',exact=True)).to_be_visible()
  OUT.mkdir(exist_ok=True,parents=True)
  for width in [1440,1024,768,390,320]:
   await page.set_viewport_size({'width':width,'height':1000})
   await goto()
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('jobs',width)
   await page.screenshot(path=str(OUT/f'jobs-{width}.png'))
   await page.get_by_role('button',name='Tags',exact=True).click()
   await page.get_by_label('Find a tag',exact=True).fill('topic')
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('filters',width)
   await page.screenshot(path=str(OUT/f'filters-{width}.png'))
   await page.get_by_role('button',name='Close tag filters').click()
   if width<1024:
    await page.get_by_label('Project',exact=True).select_option('p0')
    await expect(page).to_have_url(re.compile('project_id=p0'))
    await page.get_by_label('Folder',exact=True).select_option('f0')
    await expect(page).to_have_url(re.compile('folder_id=f0'))
   else:
    await page.get_by_label('Find a project',exact=True).fill('Research')
    nav=page.get_by_role('navigation',name='Projects',exact=True)
    assert not await nav.get_by_role('button',name=re.compile('Operations')).is_visible()
   await goto()
   await page.get_by_role('button',name='Actions for Report 01',exact=True).click()
   await page.get_by_role('menuitem',name='Edit tags',exact=True).click()
   await dialog.get_by_label('Tags',exact=True).fill(LONG)
   await dialog.get_by_label('Tags',exact=True).press('Enter')
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('editor',width)
   await page.screenshot(path=str(OUT/f'tag-editor-{width}.png'))
   box=await dialog.bounding_box();assert box['x']>=0 and box['x']+box['width']<=width,('dialog',width,box)
   await dialog.get_by_role('button',name='Cancel',exact=True).click()
  assert not errors,errors
  await ctx.close()
  anon=await browser.new_context();await anon.route('**/api/**',lambda r:r.fulfill(status=200,json={'signup_enabled':True}))
  page=await anon.new_page();await page.goto(URL+'/jobs?tag=finance');await page.wait_for_url('**/login?**');assert 'next=' in page.url
  await browser.close()
  print('Jobs workspace passed: tags, editing, status/type/search filters, history, project context, content scope, selection/move, delete confirmation/recovery, pagination, errors, auth and 320–1440px layouts. All API calls intercepted.')
asyncio.run(main())
