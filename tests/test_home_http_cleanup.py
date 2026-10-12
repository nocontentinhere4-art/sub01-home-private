import asyncio
import socket
from aiohttp import web, ClientSession, WSMsgType
from home_http import close_http_runner


def test_shutdown_closes_viewers_and_releases_local_listener():
    async def run():
        viewers=set()
        async def viewer(request):
            ws=web.WebSocketResponse()
            await ws.prepare(request);viewers.add(ws)
            try:
                async for message in ws: pass
            finally: viewers.discard(ws)
            return ws
        app=web.Application();app.router.add_get('/ws',viewer)
        runner=web.AppRunner(app,shutdown_timeout=1)
        await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0)
        await site.start();port=site._server.sockets[0].getsockname()[1]
        async with ClientSession() as client:
            ws=await client.ws_connect(f'http://127.0.0.1:{port}/ws')
            closing=asyncio.create_task(close_http_runner(runner,viewers))
            message=await asyncio.wait_for(ws.receive(),2)
            assert message.type in (WSMsgType.CLOSE,WSMsgType.CLOSED)
            await ws.close();await closing
        assert not viewers
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            probe.bind(('127.0.0.1',port))
    asyncio.run(run())
