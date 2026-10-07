"""Scroll-driven operation diagrams: run against LANDING_URL with Playwright."""
import asyncio
import os
from playwright.async_api import async_playwright

URL = os.environ.get('LANDING_URL', 'http://127.0.0.1:3108')
NAMES = ['Documents', 'Audio & video', 'Images']

async def selected(page, index):
    await page.wait_for_function('(i)=>document.querySelector(".operation-scroll").dataset.operation===String(i)', arg=index)
    assert await page.get_by_role('button', name=NAMES[index], exact=True).get_attribute('aria-pressed') == 'true'
    assert await page.locator(f'#operation-panel-{index}').is_visible()

async def main():
    async with async_playwright() as p:
        options = {'headless': True}
        if os.environ.get('CHROMIUM_PATH'):
            options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = await p.chromium.launch(**options)
        page = await browser.new_page(viewport={'width':1440,'height':900})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto(URL, wait_until='networkidle')
        await page.wait_for_function('document.querySelector(".operation-scroll").dataset.mode==="pinned"')
        for width, height in [(1440,900),(1366,768),(768,1024),(1920,650)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.wait_for_timeout(250)
            mode = await page.locator('.operation-scroll').get_attribute('data-mode')
            for index in [0,1,2,1,0]:
                if mode == 'pinned':
                    await page.evaluate('''(i)=>{const e=document.querySelector('.operation-scroll');
                      scrollTo(0,scrollY+e.getBoundingClientRect().top-92+
                        (i+.5)/3*parseFloat(e.style.getPropertyValue('--operation-travel')))}''', index)
                else:
                    await page.locator(f'#operation-panel-{index}').evaluate('(e)=>scrollTo(0,scrollY+e.getBoundingClientRect().top-92)')
                await selected(page,index)
                await page.wait_for_timeout(400)
                box = await page.locator(f'#operation-panel-{index}').bounding_box()
                assert 91 <= box['y'] <= 93, (width,mode,index,box)
                if mode == 'pinned':
                    assert box['y']+box['height'] <= height, (width,index,box)
                    assert await page.locator('.operation-canvas:visible').count() == 1
            for index in [2,0,1]:
                await page.get_by_role('button',name=NAMES[index],exact=True).click()
                await page.wait_for_timeout(200)
                await selected(page,index)
        # Resize the active step into the mobile reading layout, and back.
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_timeout(300)
        await selected(page,1)
        for width,height in [(390,844),(320,640),(844,390)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.wait_for_timeout(300)
            assert await page.locator('.operation-scroll').get_attribute('data-mode') == 'flow'
            for index in [0,1,2,1,0]:
                await page.locator(f'#operation-panel-{index}').evaluate('''(e)=>{const h=innerWidth<768?document.querySelector('.operation-picker').offsetHeight:0;
                    scrollTo(0,scrollY+e.getBoundingClientRect().top-92-h)}''')
                await selected(page,index)
                picker = await page.locator('.operation-picker').bounding_box()
                assert picker['y'] >= 71
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.get_by_role('button',name='Images',exact=True).focus()
            await page.keyboard.press('Enter')
            await selected(page,2)
        await page.set_viewport_size({'width':1440,'height':900})
        await page.wait_for_timeout(400)
        await selected(page,2)
        await page.emulate_media(reduced_motion='reduce')
        await page.wait_for_timeout(300)
        await selected(page,2)
        assert await page.locator('.operation-scroll').get_attribute('data-mode') == 'flow'
        assert await page.locator('.operation-canvas:visible').count() == 3
        await page.get_by_role('button',name='Documents',exact=True).click()
        await selected(page,0)
        assert not errors, errors
        # Server-rendered fallback keeps every operation available without JS.
        nojs = await browser.new_context(java_script_enabled=False)
        static = await nojs.new_page()
        await static.goto(URL,wait_until='domcontentloaded')
        assert await static.locator('.operation-canvas:visible').count() == 3
        await browser.close()
        print('Operation scroll passed: forward/reverse, pinned bounds, manual and keyboard navigation, mobile, resize, reduced motion and no-JS.')

asyncio.run(main())
