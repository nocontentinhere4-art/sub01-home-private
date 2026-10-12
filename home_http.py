"""Release the private home's HTTP listener and viewer sockets on shutdown."""
import asyncio


async def close_http_runner(runner, sockets, timeout=3):
    try:
        for site in list(runner.sites):
            await site.stop()
        if sockets:
            await asyncio.wait_for(asyncio.gather(
                *(ws.close(code=1001, message=b'The private home is restarting.') for ws in list(sockets)),
                return_exceptions=True,
            ), timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        await runner.cleanup()
