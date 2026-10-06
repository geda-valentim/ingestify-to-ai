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
        assert await page.locator('.secondary-title').first.evaluate("e=>getComputedStyle(e).webkitTextStrokeWidth") == '0px'
        await page.wait_for_function('document.querySelector("video")?.readyState >= 2')
        assert await page.locator('video').evaluate('(v) => v.paused && v.muted')
        # End, middle and start navigation must seek in both directions.
        for chapter in [7, 3, 6, 1, 0]:
            await page.get_by_role('button', name=f'Scene {chapter+1}:', exact=False).click()
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
            assert await page.locator('.landing-story-copy .landing-eyebrow').inner_text() == 'PLANNED / DATA LAKE DELIVERY'
        await page.get_by_role('link', name='Skip the introduction').focus()
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(150)
        assert abs((await page.locator('#operacoes').bounding_box())['y']-95) < 5
        # Full-bleed layout and interactive, animated SVG sections.
        assert await page.locator('.landing').get_attribute('lang') == 'en'
        assert (await page.locator('#operacoes').bounding_box())['width'] == 1440
        for name in ['Audio & video', 'Images', 'Documents']:
            button = page.get_by_role('button', name=name, exact=True)
            await button.click()
            assert await button.get_attribute('aria-pressed') == 'true'
        await page.get_by_role('button', name='Modal · audio').click()
        assert 'runs on Modal' in await page.locator('.compute-selection').inner_text()
        await page.get_by_role('button', name='Local', exact=True).click()
        assert 'runs locally' in await page.locator('.compute-selection').inner_text()
        await page.get_by_role('button', name='Pause motion', exact=True).click()
        assert await page.locator('.landing').get_attribute('data-motion') == 'paused'
        await page.get_by_role('button', name='Resume motion', exact=True).click()
        assert await page.locator('.landing').get_attribute('data-motion') == 'running'
        await context.grant_permissions(['clipboard-read', 'clipboard-write'])
        await page.get_by_role('button', name='Copy upload example').click()
        assert 'X-API-Key: YOUR_API_KEY' in await page.evaluate('navigator.clipboard.readText()')
        assert 'docling_preset' not in await page.evaluate('navigator.clipboard.readText()')
        await page.get_by_role('button', name='JSON result', exact=True).click()
        await page.get_by_role('button', name='Copy JSON example', exact=True).click()
        import json
        payload = json.loads(await page.evaluate('navigator.clipboard.readText()'))
        assert payload['status'] == 'completed' and payload['result']['metadata']['format'] == 'pdf'
        assert payload['result']['markdown'].startswith('# Report')
        assert 'PLANNED' in await page.locator('#data-lake .roadmap-label').inner_text()
        assert await page.locator('.lake-planned').get_by_text('PLANNED DELIVERY').is_visible()
        await page.get_by_role('button', name='Upload request', exact=True).click()
        await page.locator('summary').filter(has_text='What can I transform?').click()
        assert await page.locator('details[open]').count() == 1
        for width, height in [(1920,1080), (1920,650), (320,640), (390,844), (390,667), (768,1024), (844,390)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.evaluate('scrollTo(0,0)')
            await page.wait_for_timeout(250)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            if height < 620:
                assert await page.locator('.landing-static article').count() == 8
            else:
                box = await page.locator('.landing-story-bottom').bounding_box()
                assert box['y'] + box['height'] <= height + 1
                if width < 768:
                    film = page.locator('.landing-film')
                    frame = await film.bounding_box()
                    copy = await page.locator('.landing-story-copy').bounding_box()
                    assert frame['x'] >= 0 and frame['x'] + frame['width'] <= width + 1
                    assert frame['y'] >= copy['y'] + copy['height']
                    assert float(await film.evaluate('e=>getComputedStyle(e).opacity')) == 1
                    assert await film.evaluate('e=>getComputedStyle(e).maskImage') == 'none'
        await page.set_viewport_size({'width':1920,'height':650})
        for chapter in range(8):
            await page.get_by_role('button', name=f'Scene {chapter+1}:', exact=False).click()
            await page.wait_for_timeout(150)
            box = await page.locator('.landing-story-copy').bounding_box()
            bottom = await page.locator('.landing-story-bottom').bounding_box()
            assert box['y'] >= 72, (chapter, box)
            assert box['y'] + box['height'] < bottom['y'], (chapter, box, bottom)
        await context.close()
        mobile = await browser.new_context(viewport={'width':390,'height':844})
        page = await mobile.new_page()
        await page.goto(URL, wait_until='networkidle')
        await page.wait_for_function('document.querySelector("video")?.readyState >= 2')
        assert 'ingestify-scroll-mobile.mp4' in await page.locator('video').evaluate('(v)=>v.currentSrc')
        await mobile.close()
        # Accessibility preferences must prevent downloading the video entirely.
        reduced = await browser.new_context(reduced_motion='reduce')
        page = await reduced.new_page()
        videos = []
        page.on('request', lambda r: videos.append(r.url) if '.mp4' in r.url else None)
        await page.goto(URL, wait_until='networkidle')
        assert await page.locator('.landing-static article').count() == 8
        assert not videos
        await page.locator('#api').scroll_into_view_if_needed()
        assert await page.locator('.api-sequence').evaluate("e=>getComputedStyle(e,'::before').transform") == 'none'
        await page.evaluate('scrollBy(0,150)')
        assert await page.locator('.api-sequence').evaluate("e=>getComputedStyle(e,'::before').transform") == 'none'
        await reduced.close()
        # Media failure must retain navigation and the relevant static frame.
        fallback = await browser.new_context(viewport={'width':1440,'height':900})
        page = await fallback.new_page()
        await page.route('**/*.mp4', lambda route: route.abort())
        await page.goto(URL, wait_until='networkidle')
        await page.get_by_role('button', name='Scene 4: Images').click()
        await page.wait_for_timeout(250)
        assert 'scene-04' in await page.locator('.landing-film img').get_attribute('src')
        assert await page.get_by_role('link', name='Explore image operations').is_visible()
        assert not errors, errors
        await browser.close()
        print('Landing browser: video forward/reverse/stop, future labels, chapters, skip, FAQ, viewport layouts, reduced motion and media fallback passed.')

asyncio.run(main())
