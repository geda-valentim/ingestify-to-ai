"""Acceptance checks for the commercial agents page (Playwright)."""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright
URL=os.environ.get('LANDING_URL','http://127.0.0.1:3108').rstrip('/')
OUT=Path(os.environ.get('SCREENSHOT_DIR','/data/tmp/ingestify/agents-preview'))

async def main():
 async with async_playwright() as p:
  options={'headless':True}
  if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
  browser=await p.chromium.launch(**options)
  context=await browser.new_context(viewport={'width':1440,'height':900},permissions=['clipboard-read','clipboard-write'])
  page=await context.new_page();errors=[];api_calls=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('request',lambda r:api_calls.append(r.url) if '/api/' in r.url else None)
  response=await page.goto(URL+'/agents',wait_until='networkidle')
  assert response.status==200
  assert await page.locator('h1').count()==1
  assert 'Give your agents' in await page.locator('h1').inner_text()
  group=page.get_by_role('group',name='Explore the agent workflow')
  for name,text,request in [('Track','Long jobs. Short tool calls.','/jobs/JOB_ID'),('Read','Bring back the pages that matter.','/pages/4/result'),('Search','Find the work already done.','query=quarterly'),('Ingest','Ask for the data. Get a job ID.','file=@report.pdf')]:
   button=group.get_by_role('button',name=name,exact=False)
   await button.click()
   assert await button.get_attribute('aria-pressed')=='true'
   assert await page.get_by_role('heading',name=text,exact=True).is_visible()
   await page.get_by_role('button',name='Copy agent request').click()
   assert request in await page.evaluate('navigator.clipboard.readText()')
  await group.get_by_role('button',name='Search',exact=False).focus()
  await page.keyboard.press('Enter')
  assert await page.get_by_role('heading',name='Find the work already done.').is_visible()
  await page.get_by_role('button',name='Pause diagram motion').click()
  signal=page.locator('#agent-workflow-panel svg path').nth(1)
  assert await signal.evaluate('(e)=>getComputedStyle(e).animationPlayState')=='paused'
  await page.get_by_role('button',name='Resume diagram motion').click()
  assert await signal.evaluate('(e)=>getComputedStyle(e).animationPlayState')=='running'
  await page.locator('summary').filter(has_text='Can I use MCP?').click()
  assert 'not included today' in await page.locator('details[open]').inner_text()
  await page.locator('summary').filter(has_text='Does a project-bound API key isolate an agent?').click()
  assert 'not a separate authorization boundary' in await page.locator('details[open]').filter(has_text='Does a project-bound').inner_text()
  OUT.mkdir(parents=True,exist_ok=True)
  for width,height in [(1440,900),(1920,1080),(768,1024),(390,844),(320,640)]:
   await page.set_viewport_size({'width':width,'height':height})
   await page.evaluate('scrollTo(0,0)');await page.wait_for_timeout(200)
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
   await page.screenshot(path=str(OUT/f'{width}-hero.png'))
   for selector,name in [('#workflow','workflow'),('#data-platform','data'),('#integration','integration')]:
    await page.locator(selector).scroll_into_view_if_needed();await page.wait_for_timeout(200)
    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,name)
    await page.screenshot(path=str(OUT/f'{width}-{name}.png'))
   await page.goto(URL+'/',wait_until='networkidle')
   assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('home',width)
   assert await page.get_by_role('navigation',name='Footer links').get_by_role('link',name='Agents').is_visible()
   await page.goto(URL+'/agents',wait_until='networkidle')
  assert not api_calls,api_calls
  assert not errors,errors
  await context.close()
  nojs=await browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
  page=await nojs.new_page();await page.goto(URL+'/agents',wait_until='load')
  assert await page.locator('h1').is_visible()
  assert 'Keep the agent focused.' in await page.locator('main').inner_text()
  assert await page.get_by_role('link',name='Read the documentation',exact=False).get_attribute('href')=='/docs'
  await page.locator('summary').filter(has_text='Can I use MCP?').click()
  assert 'not included today' in await page.locator('details[open]').inner_text()
  assert '/agents' in await (await page.request.get(URL+'/sitemap.xml')).text()
  assert '/agents' in await (await page.request.get(URL+'/llms.txt')).text()
  await nojs.close()
  reduced=await browser.new_context(reduced_motion='reduce')
  page=await reduced.new_page();await page.goto(URL+'/agents',wait_until='networkidle')
  await page.locator('#workflow').scroll_into_view_if_needed()
  assert await page.locator('#agent-workflow-panel svg path').nth(1).evaluate('(e)=>getComputedStyle(e).animationName')=='none'
  await browser.close()
  print('Agents page passed: workflow, copy, keyboard, pause, reduced motion, no-JS content, FAQ, discovery and320–1920px layouts. No API jobs or inference requests.')

asyncio.run(main())
