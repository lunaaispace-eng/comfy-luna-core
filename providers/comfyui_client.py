"""Unified async HTTP client for ComfyUI endpoints.

Single source for the ComfyUI server URL and all HTTP interactions.
Other modules (node_registry, auto_generator, tools) should use this
client instead of creating their own aiohttp sessions.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("luna_core.providers")

# Default ComfyUI server URL — can be overridden at init
DEFAULT_URL = "http://127.0.0.1:8188"


class ComfyUIClient:
    """Async HTTP client for ComfyUI server endpoints."""

    def __init__(self, base_url: str = DEFAULT_URL):
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=15)

    async def get_json(self, path: str) -> Optional[Dict[str, Any]]:
        """GET a JSON endpoint. Returns None on failure."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}{path}",
                    timeout=self._timeout,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.debug("GET %s returned %d", path, resp.status)
                    return None
        except Exception as e:
            logger.debug("GET %s failed: %s", path, e)
            return None

    async def post_json(self, path: str, data: Any = None) -> Optional[Dict[str, Any]]:
        """POST JSON to an endpoint. Returns None on failure."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}{path}",
                    json=data,
                    timeout=self._timeout,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.debug("POST %s returned %d", path, resp.status)
                    return None
        except Exception as e:
            logger.debug("POST %s failed: %s", path, e)
            return None

    # ----- Convenience methods for common endpoints -----

    async def get_object_info(self) -> Optional[Dict[str, Any]]:
        """Fetch all node definitions from /object_info."""
        return await self.get_json("/object_info")

    async def get_queue(self) -> Optional[Dict[str, Any]]:
        """Get current queue state."""
        return await self.get_json("/queue")

    async def get_history(self, prompt_id: str = "") -> Optional[Dict[str, Any]]:
        """Get execution history."""
        path = f"/history/{prompt_id}" if prompt_id else "/history"
        return await self.get_json(path)

    async def queue_prompt(self, prompt: Dict[str, Any], client_id: str = "") -> Optional[Dict[str, Any]]:
        """Queue a prompt for execution."""
        data: Dict[str, Any] = {"prompt": prompt}
        if client_id:
            data["client_id"] = client_id
        return await self.post_json("/prompt", data)

    async def get_system_stats(self) -> Optional[Dict[str, Any]]:
        """Get ComfyUI system stats (VRAM, RAM, etc.)."""
        return await self.get_json("/system_stats")

    async def interrupt(self) -> bool:
        """Interrupt current execution."""
        result = await self.post_json("/interrupt")
        return result is not None

    async def is_available(self) -> bool:
        """Check if ComfyUI server is reachable."""
        result = await self.get_json("/system_stats")
        return result is not None
