"""
Lumen Async Utilities
Provides helpers for running async code in different thread contexts.
"""
import asyncio
import concurrent.futures

def run_async_task(coro):
    """
    Runs an async coroutine, handling environments where an event loop is already running.
    Useful for eager Celery task executions in tests.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(coro))
            return future.result()
    else:
        return asyncio.run(coro)
