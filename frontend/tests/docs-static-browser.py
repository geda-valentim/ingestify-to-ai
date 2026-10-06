"""Verify docs have real HTML without JS, plus progressive navigation and copying.

LANDING_URL=http://127.0.0.1:3108 CHROMIUM_PATH=/path/to/chrome python tests/docs-static-browser.py
"""
import asyncio
import os
from html.parser import HTMLParser
from urllib.parse import urlsplit
from xml.etree import ElementTree
from playwright.async_api import async_playwright

URL = os.environ.get('LANDING_URL', 'http://127.0.0.1:3108').rstrip('/')

class ArticleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_main = False
        self.skip = 0
        self.text = []
        self.h1 = 0
        self.canonical = None
        self.description = None
        self.languages = set()
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'template'):
            self.skip += 1
        if tag == 'main' and a.get('id') == 'docs-content':
            self.in_main = True
        if tag == 'h1' and self.in_main:
            self.h1 += 1
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'link' and a.get('rel') == 'alternate':
            self.languages.add(a.get('hreflang'))
        if tag == 'meta' and a.get('name') == 'description':
            self.description = a.get('content')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'template'):
            self.skip -= 1
        if tag == 'main':
            self.in_main = False
    def handle_data(self, data):
        if self.in_main and not self.skip:
            self.text.append(data)

async def main():
    async with async_playwright() as p:
        options = {'headless': True}
        if os.environ.get('CHROMIUM_PATH'):
            options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = await p.chromium.launch(**options)
        nojs = await browser.new_context(java_script_enabled=False, viewport={'width':390,'height':844})
        sitemap = await nojs.request.get(URL+'/sitemap.xml')
        assert sitemap.status == 200
        tree = ElementTree.fromstring(await sitemap.text())
        ns = {'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        paths = [urlsplit(item.text).path for item in tree.findall('s:url/s:loc', ns)]
        docs = [path for path in paths if '/docs' in path]
        assert len(docs) == 32 and len(set(docs)) == 32, docs
        for path in docs:
            response = await nojs.request.get(URL+path)
            assert response.status == 200, (path,response.status)
            html = await response.text()
            article = ArticleHTML(); article.feed(html)
            text = ' '.join(article.text)
            assert len(text) > 200 and article.h1 == 1, (path,len(text),article.h1)
            assert 'Loading documentation' not in text
            assert 'BAILOUT_TO_CLIENT_SIDE_RENDERING' not in html, path
            assert urlsplit(article.canonical).path == path, (path,article.canonical)
            assert article.description and {'en','pt-BR','x-default'} <= article.languages
            if path.endswith('/transcription'):
                assert 'import requests' in text and 'const API' in text and 'curl -X POST' in text
            if path.endswith('/results'):
                assert 'WEBVTT' in text and 'application/json' in text
        print('32 documentation pages contain article HTML, one H1, canonical, description and language alternates.',flush=True)
        for old, new in [('/docs?lang=pt','/pt/docs'),('/docs?lang=en','/docs'),('/docs/images?lang=pt','/pt/docs/images'),('/pt/docs/images?lang=en','/docs/images')]:
            response = await nojs.request.get(URL+old,max_redirects=0)
            assert response.status == 308, (old,response.status)
            target = urlsplit(response.headers['location'])
            assert target.path == new and not target.query, (old,target)
        assert (await nojs.request.get(URL+'/docs/nonexistent-topic')).status == 404
        assert (await nojs.request.get(URL+'/pt/docs/nonexistent-topic')).status == 404
        robots = await nojs.request.get(URL+'/robots.txt')
        assert 'Sitemap:' in await robots.text()
        llms = await nojs.request.get(URL+'/llms.txt')
        assert 'text/plain' in llms.headers['content-type']
        assert '/openapi.json' in await llms.text() and '/docs/datalakes' in await llms.text()
        page = await nojs.new_page()
        await page.goto(URL+'/docs/transcription',wait_until='load')
        assert await page.locator('#docs-content h1').is_visible()
        await page.locator('summary').filter(has_text='Python').click()
        assert await page.locator('details[open] pre').filter(has_text='import requests').is_visible()
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await page.get_by_role('link',name='Português',exact=True).click()
        await page.wait_for_url(URL+'/pt/docs/transcription')
        assert 'Transcrição' in await page.locator('#docs-content h1').inner_text()
        await page.locator('summary').filter(has_text='Explorar tópicos').click()
        await page.get_by_role('navigation',name='Tópicos da documentação').get_by_role('link',name='Imagens: descrição e OCR').click()
        await page.wait_for_url(URL+'/pt/docs/images')
        assert await page.locator('#docs-content h1').is_visible()
        print('No-JS language switch, mobile topic navigation, and native code examples passed.',flush=True)
        await nojs.close()
        interactive = await browser.new_context(viewport={'width':1440,'height':900},permissions=['clipboard-read','clipboard-write'])
        page = await interactive.new_page()
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        for old,new in [('/docs?lang=en#documentos','/docs/documents#documentos'),('/docs?lang=pt#imagens','/pt/docs/images#imagens')]:
            await page.goto(URL+old,wait_until='networkidle')
            await page.wait_for_url(URL+new)
        await page.goto(URL+'/docs/transcription',wait_until='networkidle')
        example = page.locator('details').filter(has=page.locator('summary',has_text='curl'))
        await example.get_by_role('button').click()
        assert await page.evaluate('navigator.clipboard.readText()') == await example.locator('code').inner_text()
        await page.get_by_role('link',name='Português',exact=True).click()
        await page.wait_for_url(URL+'/pt/docs/transcription')
        assert await page.locator('html').get_attribute('lang') == 'pt-BR'
        assert not errors, errors
        await browser.close()
        print('Legacy query/hash links, copy button, hydration, sitemap, robots and llms.txt passed.')

asyncio.run(main())
