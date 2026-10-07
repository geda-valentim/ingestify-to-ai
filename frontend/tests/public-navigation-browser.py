"""Verify consistent public navigation, English copy and usable native mobile menus."""
import asyncio
import os
from playwright.async_api import async_playwright, expect

URL = os.environ.get('LANDING_URL', 'http://localhost:3115').rstrip('/')
PAGES = ('/', '/agents', '/business', '/docs', '/docs/platform-start', '/login', '/register')
LINKS = ('/#operacoes', '/agents', '/business', '/docs',
         'https://github.com/geda-valentim/ingestify-to-ai', '/login')

async def main():
    async with async_playwright() as p:
        options = {'headless': True}
        if os.environ.get('CHROMIUM_PATH'):
            options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = await p.chromium.launch(**options)
        for enabled in (False, True):
            for width in (320, 768, 1440):
                context = await browser.new_context(java_script_enabled=enabled,
                    viewport={'width': width, 'height': 900}, reduced_motion='reduce')
                page = await context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for path in PAGES:
                    response = await page.goto(URL+path, wait_until='networkidle')
                    assert response.status == 200, path
                    header = page.locator('header[data-public-header]')
                    await expect(header).to_have_count(1)
                    assert await header.get_attribute('lang') == 'en'
                    await expect(header.get_by_role('link', name='Ingestify home', exact=True)).to_be_visible()
                    assert round((await header.bounding_box())['height']) == 72, (path, width)
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (path,width)
                    if width < 1000:
                        toggle = header.get_by_role('button', name='Menu', exact=True)
                        await toggle.focus()
                        await page.keyboard.press('Enter')
                        nav = header.get_by_role('navigation', name='Mobile navigation', exact=True)
                    else:
                        nav = header.get_by_role('navigation', name='Main navigation', exact=True)
                    await expect(nav).to_be_visible()
                    hrefs = await nav.locator('a').evaluate_all('(links)=>links.map(link=>link.getAttribute("href"))')
                    assert tuple(hrefs) == LINKS, (path, hrefs)
                    for label in ('Platform', 'Agents', 'Business', 'Docs', 'Sign in'):
                        await expect(nav.get_by_role('link', name=label, exact=True)).to_be_visible()
                    current = {'/':'Platform','/agents':'Agents','/business':'Business',
                               '/docs':'Docs','/docs/platform-start':'Docs'}.get(path)
                    if current:
                        await expect(nav.get_by_role('link', name=current, exact=True)).to_have_attribute('aria-current','page')
                    if path == '/' and enabled:
                        await header.get_by_role('button',name='Pause motion',exact=True).click()
                        await expect(page.locator('.landing')).to_have_attribute('data-motion','paused')
                        await header.get_by_role('button',name='Resume motion',exact=True).click()
                        await expect(page.locator('.landing')).to_have_attribute('data-motion','running')
                    if width < 1000 and enabled:
                        await nav.get_by_role('link',name='Business',exact=True).focus()
                        await page.keyboard.press('Escape')
                        await expect(toggle).to_be_focused()
                        assert await header.locator('details').get_attribute('open') is None
                    if path == '/business':
                        assert await page.locator('main').evaluate('(el)=>el.closest("[lang]").lang') == 'en'
                        await expect(page.locator('meta[property="og:locale"]')).to_have_attribute('content','en_US')
                        await expect(page.get_by_role('link',name='Process a file',exact=True)).to_be_visible()
                        assert await page.locator('main a[href^="/pt/"]').count() == 0
                        text = await page.locator('main').inner_text()
                        for old in ('Documentos','Agências','Começar','Questões','Seu próximo'):
                            assert old not in text, old
                assert not errors, errors
                # The mobile menu is a real navigation path, including without JS.
                if width < 1000:
                    await page.goto(URL+'/docs',wait_until='networkidle')
                    await page.locator('header').get_by_role('button',name='Menu',exact=True).click()
                    await page.get_by_role('navigation',name='Mobile navigation',exact=True).get_by_role('link',name='Business',exact=True).click()
                    await page.wait_for_url(URL+'/business')
                    await expect(page.locator('main h1')).to_be_visible()
                await context.close()
                print(f'PASS shared English navigation across {len(PAGES)} pages, {width}px, JavaScript={enabled}.', flush=True)

        context = await browser.new_context(viewport={'width':1440,'height':900})
        await context.add_init_script("""localStorage.setItem('auth-storage', JSON.stringify({
          state:{token:'browser-test-token',user:{id:'browser-test',username:'Test',email:'test@example.com',is_admin:false}},version:0
        }));""")
        await context.route('**/api/**', lambda route: route.fulfill(status=200,content_type='application/json',body='{}'))
        page = await context.new_page()
        for path in ('/','/agents','/business','/docs'):
            await page.goto(URL+path,wait_until='networkidle')
            account = page.locator('header').get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Open dashboard',exact=True)
            await expect(account).to_have_attribute('href','/dashboard')
        await context.close()
        await browser.close()
        print('PASS authenticated dashboard action is consistent on the public site.',flush=True)

asyncio.run(main())
