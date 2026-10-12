import asyncio
from types import SimpleNamespace
from tests.test_home_api import client

def test_browser_navigation_requires_owner_and_valid_public_address():
    async def run():
        c, live = await client()
        calls = []
        async def navigate(device, url):
            calls.append((device, url))
            return {'device':device,'title':'Python tutorial','url':url}
        async def on_screen(status):
            calls.append(status['title'])
        live.browser = SimpleNamespace(navigate=navigate)
        live.on_screen = on_screen
        headers = {'X-Admin-Token':'test'}
        try:
            assert (await c.post('/api/home/browser',json={'url':'https://docs.python.org/3/tutorial/'})).status == 403
            for url in ('file:///etc/passwd','http://127.0.0.1:8799','javascript:alert(1)'):
                assert (await c.post('/api/home/browser',json={'url':url},headers=headers)).status == 400
            assert not calls
            response = await c.post('/api/home/browser',json={'url':'https://docs.python.org/3/tutorial/'},headers=headers)
            assert response.status == 200
            assert calls == [('desk','https://docs.python.org/3/tutorial/'),'Python tutorial']
            response = await c.post('/api/home/browser',json={'device':'phone','url':'https://docs.python.org/3/tutorial/'},headers=headers)
            assert response.status == 200
            assert calls[-2:] == [('phone','https://docs.python.org/3/tutorial/'),'Python tutorial']
            live.home.node = 'bathroom'
            live.home.position = [-1.5,4.65,1.35]
            assert (await c.post('/api/home/browser',json={'url':'https://docs.python.org/3/tutorial/'},headers=headers)).status == 409
            assert len(calls) == 4
        finally:
            await c.close()
    asyncio.run(run())
