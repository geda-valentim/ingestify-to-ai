"""Check the public Business page, discovery links and usable mobile layout.

LANDING_URL=http://localhost:3113 CHROMIUM_PATH=/path/to/chrome python tests/business-browser.py
"""
import asyncio
import os
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect

URL = os.environ.get('LANDING_URL', 'http://localhost:3113').rstrip('/')

async def main():
    async with async_playwright() as p:
        options = {'headless': True}
        if os.environ.get('CHROMIUM_PATH'):
            options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = await p.chromium.launch(**options)
        static = await browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
        page = await static.new_page()
        response = await page.goto(URL+'/business',wait_until='load')
        assert response.status == 200
        assert await page.locator('main h1').count() == 1
        assert await page.locator('main h1').is_visible()
        assert await page.locator('[lang="pt-BR"]').count() > 0
        assert 'Ingestify for Business' in await page.title()
        canonical = await page.locator('link[rel="canonical"]').get_attribute('href')
        assert urlsplit(canonical).path == '/business'
        assert await page.locator('meta[name="description"]').get_attribute('content')
        assert await page.locator('figure').count() >= 2
        body = await page.locator('main').inner_text()
        for term in ('Agências e integradores','Produtos e agentes de IA','Equipes de dados','Amazon S3','MinIO','Google Cloud Storage','Azure Blob Storage','customer_id','JSONL','Full Analysis'):
            assert term in body, term
        links = await page.locator('a[href]').evaluate_all('(links)=>links.map(link=>link.getAttribute("href"))')
        paths = {urlsplit(link).path for link in links if link.startswith('/')}
        assert {'/convert','/agents','/pt/docs/platform-start'} <= paths
        for path in paths:
            result = await static.request.get(URL+path)
            assert result.status == 200, (path,result.status)
        for path in ('/','/agents','/docs','/pt/docs'):
            response = await static.request.get(URL+path)
            assert response.status == 200
            assert 'href="/business"' in await response.text(), path
        sitemap = await static.request.get(URL+'/sitemap.xml')
        assert '/business</loc>' in await sitemap.text()
        llms = await static.request.get(URL+'/llms.txt')
        assert '/business)' in await llms.text()
        await static.close()
        for width in (320,390,768,1440):
            context = await browser.new_context(viewport={'width':width,'height':900},reduced_motion='reduce')
            page = await context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            response = await page.goto(URL+'/business',wait_until='networkidle')
            assert response.status == 200
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
            await page.keyboard.press('Tab')
            await expect(page.get_by_role('link',name='Ir para o conteúdo',exact=True)).to_be_focused()
            await page.keyboard.press('Enter')
            await page.wait_for_url(URL+'/business#business-content')
            assert urlsplit(page.url).fragment == 'business-content'
            for details in await page.locator('details').all():
                await details.locator('summary').click()
                assert await details.get_attribute('open') is not None
                assert await details.locator('p').is_visible()
            assert not errors, errors
            await page.screenshot(path=f'/tmp/ingestify-business-{width}.png',full_page=True)
            await context.close()
            print(f'PASS Business public navigation, FAQ, keyboard and layout at {width}px.',flush=True)
        for width in (320,1440):
            context = await browser.new_context(viewport={'width':width,'height':900},reduced_motion='reduce')
            page = await context.new_page()
            for path in ('/','/agents','/docs'):
                await page.goto(URL+path,wait_until='networkidle')
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (path,width)
                if path == '/docs' and width == 320:
                    await page.get_by_role('button',name='Menu',exact=True).click()
                    menu = page.get_by_role('navigation',name='Mobile navigation',exact=True)
                    await expect(menu.get_by_role('link',name='Business',exact=True)).to_be_visible()
                    await menu.get_by_role('link',name='Business',exact=True).click()
                    await page.wait_for_url(URL+'/business')
                    await expect(page.locator('main h1')).to_be_visible()
                else:
                    assert await page.locator('a[href="/business"]:visible').count() > 0, (path,width)
            await context.close()
        print('PASS Business discovery links and surrounding navigation on desktop and mobile.',flush=True)
        await browser.close()
        print('PASS Business static content, metadata, internal links, sitemap and llms discovery.',flush=True)

asyncio.run(main())
