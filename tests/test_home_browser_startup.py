"""Concurrent real LocalBrowser.ensure calls share one child; no browser launch."""
import asyncio
import os
from types import SimpleNamespace
from browse_service import LocalBrowser


def test_operator_and_brain_ensure_cannot_spawn_two_children():
    async def run():
        service=LocalBrowser();spawns=[]
        async def spawn():
            await asyncio.sleep(0)
            spawns.append('fixture child');service.proc=SimpleNamespace(pid=os.getpid(),returncode=None)
            return True
        service.spawn=spawn
        status=await asyncio.gather(service.ensure(),service.ensure())
        assert status==['started','ok'] and spawns==['fixture child']
        service.proc=None
        await service.client.aclose()
    asyncio.run(run())
