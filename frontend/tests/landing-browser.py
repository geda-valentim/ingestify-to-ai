"""Browser acceptance checks. Run with Playwright against a built landing page.

LANDING_URL=http://127.0.0.1:3107 CHROMIUM_PATH=/path/to/chrome python tests/landing-browser.py
"""
import asyncio
import os
from playwright.async_api import async_playwright

URL = os.environ.get('LANDING_URL', 'http://127.0.0.1:3107')

async def main():
    async with async_playwright() as p:
        options = {'headless': True}
        if os.environ.get('CHROMIUM_PATH'):
            options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = await p.chromium.launch(**options)
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto(URL, wait_until='networkidle')
        assert await page.locator('h1').count() == 1
        await page.wait_for_function('document.querySelector("video")?.readyState >= 2')
        assert await page.locator('video').evaluate('(v) => v.paused && v.muted')
        # End, middle and start navigation must seek in both directions.
        for chapter in [7, 3, 6, 1, 0]:
            await page.get_by_role('button', name=f'Cena {chapter+1}:', exact=False).click()
            await page.wait_for_function('(n)=>document.querySelector(".landing-story-copy").dataset.chapter === String(n)', arg=chapter)
            expected = (chapter * 2 + (.25 - .08) / .76) * 3
            await page.wait_for_function('(t)=>Math.abs(document.querySelector("video").currentTime-t)<.1', arg=expected)
        stopped = await page.locator('video').evaluate('(v)=>v.currentTime')
        await page.wait_for_timeout(500)
        assert abs(stopped - await page.locator('video').evaluate('(v)=>v.currentTime')) < .05
        # The future label appears before planned objects and stays through the exit.
        for segment in [11.1, 12.5, 13.8]:
            await page.evaluate('(s)=>{let e=document.querySelector(".landing-story");scrollTo(0,scrollY+e.getBoundingClientRect().top-72+s/15*(e.offsetHeight-(innerHeight-72)))}', segment)
            await page.wait_for_timeout(150)
            assert await page.locator('.landing-story-copy .landing-eyebrow').inner_text() == 'VISÃO DE EVOLUÇÃO'
        await page.get_by_role('link', name='Pular apresentação').focus()
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(150)
        assert abs((await page.locator('#operacoes').bounding_box())['y']-95) < 5
        await page.get_by_text('O que posso transformar?', exact=True).click()
        assert await page.locator('details[open]').count() == 1
        for width, height in [(390,844), (390,667), (768,1024), (844,390)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.evaluate('scrollTo(0,0)')
            await page.wait_for_timeout(250)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            if height < 620:
                assert await page.locator('.landing-static article').count() == 8
            else:
                box = await page.locator('.landing-story-bottom').bounding_box()
                assert box['y'] + box['height'] <= height + 1
        await context.close()
        # Accessibility preferences must prevent downloading the video entirely.
        reduced = await browser.new_context(reduced_motion='reduce')
        page = await reduced.new_page()
        videos = []
        page.on('request', lambda r: videos.append(r.url) if '.mp4' in r.url else None)
        await page.goto(URL, wait_until='networkidle')
        assert await page.locator('.landing-static article').count() == 8
        assert not videos
        await reduced.close()
        # Media failure must retain navigation and the relevant static frame.
        fallback = await browser.new_context(viewport={'width':1440,'height':900})
        page = await fallback.new_page()
        await page.route('**/*.mp4', lambda route: route.abort())
        await page.goto(URL, wait_until='networkidle')
        await page.get_by_role('button', name='Cena 4: Imagens').click()
        await page.wait_for_timeout(250)
        assert 'scene-04' in await page.locator('.landing-film img').get_attribute('src')
        assert await page.get_by_role('link', name='Operações de imagem').is_visible()
        assert not errors, errors
        await browser.close()
        print('Landing browser: video forward/reverse/stop, future labels, chapters, skip, FAQ, viewport layouts, reduced motion and media fallback passed.')

asyncio.run(main())
