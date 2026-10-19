import aiohttp
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any

logger = logging.getLogger(__name__)


class ArrClient:
    """Session handling and requests shared by the Sonarr and Radarr clients."""

    # Used in log lines; set by each subclass.
    service = "arr"

    def __init__(self, base_url: str, api_key: str):
        """Initialize the client.

        Args:
            base_url: Base URL of the instance (e.g., http://radarr:7878)
            api_key: The instance's API key
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        """Return a lazily-created, reused HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    @asynccontextmanager
    async def _session_ctx(self):
        """Yield the shared session without closing it on exit."""
        yield self._get_session()

    async def close(self) -> None:
        """Close the shared HTTP session (call on shutdown)."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, **kwargs) -> tuple[int, Any]:
        """Send a request and return (status, parsed body). Status is 0 if it never got a response."""
        url = f"{self.base_url}{path}"
        try:
            async with self._session_ctx() as session:
                async with session.request(method, url, headers=self.headers, **kwargs) as resp:
                    if resp.content_type == "application/json":
                        return resp.status, await resp.json()
                    return resp.status, await resp.text()
        except Exception as e:
            logger.error(f"{self.service} {method} {path} failed: {e}")
            return 0, None
