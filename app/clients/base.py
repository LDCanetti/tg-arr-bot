import asyncio
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

    # --- Queue / manual import ------------------------------------------------
    #
    # Same endpoints in Sonarr and Radarr (api/v3); subclasses only say which
    # related records to embed in queue items.
    QUEUE_INCLUDES: dict = {}

    async def get_queue(self) -> Optional[list]:
        """Every item in the Activity queue, or None if the service couldn't be reached."""
        params = {"page": "1", "pageSize": "1000", **self.QUEUE_INCLUDES}
        status, body = await self._request("GET", "/api/v3/queue", params=params)
        if status == 200:
            return body.get("records", [])
        logger.error(f"{self.service} get queue error: {status} - {body}")
        return None

    async def get_manual_import(self, download_id: str) -> Optional[list]:
        """The files in a download as the Manual Import dialog sees them, rejections included."""
        status, body = await self._request("GET", "/api/v3/manualimport", params={"downloadId": download_id})
        if status == 200:
            return body
        logger.error(f"{self.service} get manual import error: {status} - {body}")
        return None

    async def manual_import(self, files: list) -> Optional[int]:
        """Run the ManualImport command, as the dialog's Import button does. Returns the command id.

        importMode "auto" lets the app move or copy depending on the download
        client, the same as the web UI does for queue items.
        """
        payload = {"name": "ManualImport", "files": files, "importMode": "auto"}
        status, body = await self._request("POST", "/api/v3/command", json=payload)
        if status in (200, 201):
            return body.get("id")
        logger.error(f"{self.service} manual import error: {status} - {body}")
        return None

    async def wait_for_command(self, command_id: int, timeout: float = 10) -> Optional[dict]:
        """Poll a command until it finishes or the timeout passes; returns its last state.

        Kept short: updates are handled one at a time, so this wait holds up the bot.
        """
        command = None
        for _ in range(int(timeout / 2)):
            status, body = await self._request("GET", f"/api/v3/command/{command_id}")
            if status == 200:
                command = body
                if body.get("status") in ("completed", "failed", "aborted", "cancelled", "orphaned"):
                    break
            await asyncio.sleep(2)
        return command

    async def remove_queue_item(self, queue_id: int, blocklist: bool, search_again: bool) -> bool:
        """Remove a download from the queue and the download client, like the queue's Remove dialog.

        Blocklisting marks the release failed; unless skipRedownload is set the
        app then searches for a replacement (if "Redownload Failed" is on, the
        default).
        """
        params = {
            "removeFromClient": "true",
            "blocklist": "true" if blocklist else "false",
            "skipRedownload": "false" if search_again else "true",
        }
        status, body = await self._request("DELETE", f"/api/v3/queue/{queue_id}", params=params)
        if status in (200, 204):
            logger.info(f"{self.service}: removed queue item {queue_id} (blocklist={blocklist}, search={search_again})")
            return True
        logger.error(f"{self.service} remove queue item error: {status} - {body}")
        return False
