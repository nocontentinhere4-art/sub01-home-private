"""Bounded real browser input on owned, routed pages; no network or main life state."""
import asyncio
import time
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import browse
from browse_service import BrowserClient, FrameChanged, make_app
from home_api import add_home_routes

URL = 'https://example.org/reading'
PAGE = '<html><title>Reading about Tokyo houses</title><body><main style="height:2200px">' + (
    '<p>Wooden houses and gardens line the quiet streets.</p>' * 60) + '</main></body></html>'
NOTICE = '<div role="dialog" style="position:fixed;inset:100px;background:white"><p>Newsletter notice</p><button id="close" onclick="this.parentElement.remove()">Close</button></div>'
WALL = '<div role="dialog" style="position:fixed;inset:100px;background:white"><h2>Support Journalism That Matters</h2><p>Ads keep our content free.</p><p>Please consider allowing ads. Thank you!</p><button id="allow">ALLOW ADS</button></div>'


def test_real_scroll_close_back_revision_and_safe_refusal():
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            br = await pw.chromium.launch(headless=True)
            ctx = await br.new_context(viewport={'width':800, 'height':600})
            async def route(r):
                if r.request.url.startswith('https://example.org/'):
                    await r.fulfill(status=200, content_type='text/html', body=PAGE)
                else:
                    await r.abort()
            await ctx.route('**/*', route)
            page = await ctx.new_page()
            b = browse.Browser(sessions={}, decide=True)
            sc = b.screens['desk']
            sc.page, sc.ctx = page, ctx
            await page.goto(URL)
            sc.info = {'url':URL, 'title':'Reading about Tokyo houses', 'host':'example.org', 'kind':'page', 'why':'fixture', 't':time.time()}
            assert await b._shoot(sc)
            server = TestServer(make_app(b, token='owned-token'))
            await server.start_server()
            client = BrowserClient(str(server.make_url('')).rstrip('/'), token='owned-token')
            raw_client = TestClient(server)
            try:
                old = sc.frame_id
                await b.lock.acquire()
                try:
                    assert (await client.operator_action('desk','scroll_down',old))['error']=='busy'
                    assert await page.evaluate('window.scrollY')==0
                finally:
                    b.lock.release()
                sc.awaiting = {'frame_id':old, 'links':[]}
                # Real authenticated service/client transport and current JPEG revision.
                raw, revision = await client.frame('desk', old)
                assert raw[:2] == b'\xff\xd8' and revision == old
                result = await client.operator_action('desk', 'scroll_down', old)
                assert result['ok'] and await page.evaluate('window.scrollY') == 420
                assert result['status']['frame_id'] != old and sc.awaiting is None
                assert sc.next_at > time.time()+25
                assert await b.step('desk') is None
                with pytest.raises(FrameChanged):
                    await client.frame('desk', old)
                # Replayed input must not act, nor consume a newly prepared brain choice.
                pending = {'frame_id':sc.frame_id, 'links':[]}
                sc.awaiting = pending
                assert (await client.operator_action('desk', 'scroll_up', old))['error'] == 'stale'
                assert await b.act('desk', {'action':'leave','frame_id':old}) is None
                assert sc.awaiting is pending
                assert (await client.operator_action('desk', 'scroll_up', sc.frame_id))['ok']
                assert await page.evaluate('window.scrollY') == 0
                await page.evaluate('(html)=>document.body.insertAdjacentHTML("beforeend",html)', NOTICE)
                assert await b._shoot(sc)
                b.dismissed = [{'fixture':i} for i in range(100)]  # capped log still detects one new close
                result = await client.operator_action('desk', 'close_notice', sc.frame_id)
                assert result['ok'] and await page.locator('#close').count() == 0
                result = await client.operator_action('desk', 'close_notice', sc.frame_id)
                assert not result['ok'] and result['message']=='No safe close button on this page'
                # Back uses the real guarded _open/_settle path, not browser go_back.
                sc.history = ['https://example.org/previous', URL]
                result = await client.operator_action('desk', 'back', sc.frame_id)
                assert result['ok'] and page.url=='https://example.org/previous'
                assert sc.history[-1]=='https://example.org/previous'
                # A formerly public page gaining a wall is refused before any button press.
                await page.evaluate('window.clicked=[];document.addEventListener("click",e=>window.clicked.push(e.target.id));')
                await page.evaluate('(html)=>document.body.insertAdjacentHTML("beforeend",html)', WALL)
                result = await client.operator_action('desk', 'close_notice', sc.frame_id)
                assert result['error']=='refused' and result['closed']=='desk'
                assert page.url=='about:blank' and sc.shot is None and sc.awaiting is None
                assert b.dismissed[-1].get('label')=='Close'  # no ALLOW ADS appended
                # Transport authentication is still enforced.
                r = await raw_client.post('/operator-action', json={'device':'desk','action':'scroll_down','frame_id':old})
                assert r.status==401
                assert (await client.operator_action('desk','click',old))['error']=='invalid'
            finally:
                if client.http:
                    await client.http.close()
                await raw_client.close()
                await br.close()
    asyncio.run(run())


def test_operator_home_auth_privacy_and_stale_contract():
    async def run():
        calls, observed = [], []
        privacy = False
        async def action(device, verb, revision):
            calls.append((device,verb,revision))
            return {'ok':False,'error':'stale','message':'Refresh its frame'}
        async def on_screen(status):
            observed.append(status)
        live = SimpleNamespace(home=SimpleNamespace(view=lambda:{'privacy':privacy}),
                               browser=SimpleNamespace(operator_action=action),on_screen=on_screen)
        app = web.Application()
        add_home_routes(app, live, lambda r:r.headers.get('X-Admin-Token')=='owned')
        c = TestClient(TestServer(app))
        await c.start_server()
        data = {'device':'phone','action':'scroll_down','frame_id':'owned:1'}
        try:
            assert (await c.post('/api/home/browser/action',json=data)).status==403
            privacy = True
            assert (await c.post('/api/home/browser/action',json=data,headers={'X-Admin-Token':'owned'})).status==409
            assert calls==[]
            privacy = False
            r = await c.post('/api/home/browser/action',json=data,headers={'X-Admin-Token':'owned'})
            assert r.status==409 and (await r.json())['error']=='stale'
            assert calls==[('phone','scroll_down','owned:1')] and observed==[]
            for change in ({'action':'click'},{'device':'unknown'},{'frame_id':True},{'frame_id':'x'*101}):
                assert (await c.post('/api/home/browser/action',json=data|change,headers={'X-Admin-Token':'owned'})).status==400
            assert len(calls)==1
            # An already in-flight action is not presented after privacy begins.
            async def enters_bath(device, verb, revision):
                nonlocal privacy
                privacy = True
                return {'ok':True,'status':{'frame_id':'new:2'}}
            live.browser.operator_action = enters_bath
            assert (await c.post('/api/home/browser/action',json=data,headers={'X-Admin-Token':'owned'})).status==409
            assert observed==[]
        finally:
            await c.close()
    asyncio.run(run())


def test_frame_identity_changes_across_new_browser_instances():
    assert browse.Screen('desk').frame_id != browse.Screen('desk').frame_id


def test_manual_input_does_not_queue_behind_a_reserved_lock_waiter():
    async def run():
        b = browse.Browser(sessions={})
        await b.lock.acquire()
        waiting = asyncio.create_task(b.lock.acquire())
        await asyncio.sleep(0)
        b.lock.release()
        assert not b.lock.locked()  # older waiter is woken but has not resumed yet
        result = await b.operator_action('desk','scroll_down','owned:1')
        assert result['error']=='busy'
        await waiting
        b.lock.release()
    asyncio.run(run())


@pytest.mark.parametrize('url,html', [
    ('http://127.0.0.1/private', PAGE),
    ('https://www.youtube.com/account', PAGE),
    (URL, '<html><title>Sign in</title><body><form><input type="password"><button>Sign in</button></form></body></html>'),
    (URL, '<html><title>Verify you are human</title><body>Verify you are human. Complete the CAPTCHA.</body></html>'),
], ids=['private-address', 'private-account', 'login', 'captcha'])
def test_changed_private_or_login_or_captcha_page_receives_no_operator_input(url,html):
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            br = await pw.chromium.launch(headless=True)
            try:
                page = await br.new_page()
                await page.route('**/*', lambda r:r.fulfill(status=200,content_type='text/html',body=html))
                await page.goto(url)
                b = browse.Browser(sessions={})
                sc = b.screens['phone']
                sc.page = page
                sc.info = {'url':URL,'title':'Previously safe page','kind':'page'}
                sc.shot = b'owned previous frame'
                sc.awaiting = {'links':[]}
                result = await b.operator_action('phone','close_notice',sc.frame_id)
                assert result['error']=='refused' and result['closed']=='phone'
                assert page.url=='about:blank' and sc.shot is None and sc.awaiting is None
                assert b.dismissed==[]
            finally:
                await br.close()
    asyncio.run(run())


@pytest.mark.parametrize('fail_vote', [False, True])
def test_live_leave_branches_keep_the_captured_frame(fail_vote):
    from live_server import Live
    calls = []
    class Eyes:
        def propose(self, page, interest):
            return ([{'action':'scroll'}] if fail_vote else []), {}
    async def act(device, action, why, interest):
        calls.append(action)
    async def vote(*args):
        raise RuntimeError('owned failed vote')
    live = SimpleNamespace(eyes=Eyes(),browser=SimpleNamespace(act=act),_vote_and_act=vote)
    asyncio.run(Live.decide(live,'desk',{'frame_id':'owned:123'}))
    assert calls==[{'action':'leave','frame_id':'owned:123'}]
