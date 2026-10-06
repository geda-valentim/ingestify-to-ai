"""Dashboard navigation and API states with fully intercepted synthetic sessions."""
import asyncio,json,os
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
URL=os.environ.get('LANDING_URL','http://127.0.0.1:3108').rstrip('/')
OUT=Path('/data/tmp/ingestify/dashboard-preview')
USER={'id':999999,'username':'Preview','email':'preview@example.invalid','is_admin':False}

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome'))
  ctx=await browser.new_context(viewport={'width':1440,'height':1000})
  await ctx.add_init_script('localStorage.setItem("auth-storage", '+json.dumps(json.dumps({'state':{'user':USER,'token':'local-browser-preview'},'version':0}))+');')
  mode='populated';requests=[]
  async def mock(route):
   nonlocal mode
   path=urlparse(route.request.url).path;requests.append((route.request.method,path))
   if path.endswith('/auth/me'):data=USER
   elif path.endswith('/jobs'):
    if mode=='error':return await route.fulfill(status=503,json={'detail':'Test unavailable'})
    empty=mode=='empty'
    data={'total':0 if empty else 12,'limit':5,'offset':0,'counts':{'all':0 if empty else 12,'queued':0 if empty else 2,'processing':0 if empty else 1,'completed':0 if empty else 8,'failed':0 if empty else 1,'cancelled':0},'jobs':[] if empty else [{'job_id':'test-job','name':'Quarterly report','filename':'report.pdf','status':'completed','kind':'document','type':'main','progress':100,'tags':[],'project':{'id':'project-test','name':'Research'}}]}
   elif path.endswith('/projects'):data={'projects':[{'id':'project-test','name':'Research','folders':[],'archived':False}]}
   elif path.endswith('/datalakes'):data={'connections':[]}
   else:data={}
   await route.fulfill(status=200,json=data)
  await ctx.route('**/api/**',mock)
  page=await ctx.new_page();errors=[];page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE ERROR:',str(e),flush=True)))
  OUT.mkdir(exist_ok=True)
  for width in [1440,1024,768,390,320]:
   await page.set_viewport_size({'width':width,'height':1000})
   await page.goto(URL+'/dashboard',wait_until='networkidle')
   await expect(page.get_by_role('heading',name='Your data workspace.')).to_be_visible()
   assert await page.locator('input[type=file]').count()==0
   stats=page.get_by_role('region',name='Job overview')
   for label,value in [('Total jobs','12'),('In progress','3'),('Completed','8'),('Failed','1')]:
    assert value in await stats.get_by_role('link').filter(has_text=label).inner_text()
   assert await page.get_by_role('link',name='Manage API keys').get_attribute('href')=='/api-keys'
   assert '/upload' in await page.get_by_label('Example upload request').inner_text()
   assert await page.get_by_role('link',name='Quarterly report').get_attribute('href')=='/jobs/test-job'
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
   await page.screenshot(path=str(OUT/f'dashboard-{width}.png'),full_page=True)
   if width<1280:
    await page.get_by_role('button',name='Menu',exact=True).click()
    nav=page.get_by_role('navigation',name='Mobile navigation')
   else:nav=page.get_by_role('navigation',name='Main navigation')
   assert await nav.get_by_role('link',name='Dashboard',exact=True).get_attribute('aria-current')=='page'
   await nav.get_by_role('link',name='Convert',exact=True).click()
   await page.wait_for_url(URL+'/convert')
   await expect(page.get_by_text('Convert Document',exact=True)).to_be_visible()
   assert await page.locator('input[type=file]').count()==1
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('convert',width)
  await page.goto(URL+'/dashboard?project_id=project-test&folder=Reports',wait_until='networkidle')
  assert '/convert?project_id=project-test&folder=Reports' in page.url
  await expect(page.get_by_text('Convert Document',exact=True)).to_be_visible()
  await expect(page.get_by_role('combobox').first).to_have_value('Research')
  mode='empty';await page.goto(URL+'/dashboard',wait_until='networkidle')
  await expect(page.get_by_text('Your first job starts here.',exact=True)).to_be_visible()
  mode='error';await page.reload(wait_until='networkidle')
  await expect(page.get_by_role('alert').filter(has_text='Could not refresh jobs')).to_be_visible(timeout=15000)
  assert '—' in await page.get_by_role('region',name='Job overview').inner_text()
  assert not await page.get_by_text('Your first job starts here.',exact=True).is_visible()
  mode='populated';await page.get_by_role('button',name='Retry',exact=True).click()
  await expect(page.get_by_role('link',name='Quarterly report')).to_be_visible()
  assert not errors,errors
  assert all(method=='GET' for method,path in requests),requests
  await ctx.close()
  anonymous=await browser.new_context();await anonymous.route('**/api/**',lambda r:r.fulfill(status=200,json={'signup_enabled':True}))
  page=await anonymous.new_page();await page.goto(URL+'/dashboard');await page.wait_for_url('**/login?**')
  assert 'next=%2Fdashboard' in page.url
  await browser.close()
  print('Dashboard passed: real-data UI states, recovery, API links, route migration, auth guard, 320–1440px layout and conversion navigation. All API requests intercepted.')
asyncio.run(main())
