import asyncio
import functools

import aiohttp

from . import proxy

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)

DEFAULT_HEADERS = {
    "User-Agent": "ComfyUI-AI-Executor/0.1 (+https://github.com/)",
    "Accept": "application/json",
}


async def fetch_json(url, params=None, headers=None, timeout=DEFAULT_TIMEOUT):
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    async with aiohttp.ClientSession(timeout=timeout, headers=merged) as session:
        async with session.get(url, params=params, proxy=proxy.get_proxy()) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def fetch_bytes(url, headers=None, timeout=None, chunk_cb=None):
    timeout = timeout or aiohttp.ClientTimeout(total=None, connect=15)
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    async with aiohttp.ClientSession(timeout=timeout, headers=merged) as session:
        async with session.get(url, proxy=proxy.get_proxy()) as resp:
            resp.raise_for_status()
            buf = bytearray()
            async for chunk in resp.content.iter_chunked(1 << 16):
                buf.extend(chunk)
                if chunk_cb:
                    chunk_cb(len(buf), resp.content_length)
            return bytes(buf)


def run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def normalize_result(source, external_id, title, url, published_at=None,
                     base_model=None, samples=None, tags=None,
                     workflow_url=None, workflow=None, author=None,
                     stats=None, extra=None):
    return {
        "source": source,
        "id": str(external_id),
        "title": title or "",
        "url": url or "",
        "author": author or "",
        "published_at": published_at,
        "base_model": base_model,
        "samples": samples or [],
        "tags": tags or [],
        "workflow_url": workflow_url,
        "workflow": workflow,
        "stats": stats or {},
        "extra": extra or {},
    }
