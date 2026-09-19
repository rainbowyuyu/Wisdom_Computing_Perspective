"""Finish resource cleanup before propagating request cancellation."""
import asyncio

import anyio


async def finish_cleanup(awaitable):
    # Starlette cancels streaming handlers through an AnyIO cancel scope;
    # asyncio callers can also issue repeated Task.cancel() requests.
    cancelled = False
    with anyio.CancelScope(shield=True):
        task = asyncio.ensure_future(awaitable)
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result
