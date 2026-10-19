import logging
from typing import Optional, List, Dict, Any

from app.clients.base import ArrClient
from app.config.settings import settings

logger = logging.getLogger(__name__)


class SonarrClient(ArrClient):
    """Sonarr API client for TV series management."""

    service = "Sonarr"
    QUEUE_INCLUDES = {"includeSeries": "true", "includeEpisode": "true", "includeUnknownSeriesItems": "true"}

    async def search_series(self, query: str) -> List[Dict[str, Any]]:
        """Search for TV series by title.
        
        Args:
            query: Series title to search for
            
        Returns:
            List of matching series
        """
        url = f"{self.base_url}/api/v3/series/lookup"
        params = {"term": query}
        
        try:
            async with self._session_ctx() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Sonarr search error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Sonarr search failed: {e}")
            return []
    
    # Our button keys -> Sonarr's MonitorTypes enum (api/v3 addOptions.monitor).
    # Sonarr applies the season/episode monitoring itself; we must not hand-roll a
    # "seasons" array, or it silently overrides the choice.
    MONITOR_TYPES = {
        "all": "all",
        "future": "future",
        "missing": "missing",
        "existing": "existing",
        "recent": "recent",
        "pilot": "pilot",
        "first": "firstSeason",
        "last": "lastSeason",
        "specials": "monitorSpecials",
        "no_specials": "unmonitorSpecials",
        "none": "none",
    }

    # Whether adding with this monitor type should kick off a search straight away.
    # "future"/"existing"/"none" have nothing to go looking for.
    SEARCH_ON_ADD = {
        "all": True,
        "future": False,
        "missing": True,
        "existing": False,
        "recent": True,
        "pilot": True,
        "first": True,
        "last": True,
        "specials": True,
        "no_specials": True,
        "none": False,
    }

    async def add_series(self, series_id: int, title: str = "", root_folder_path: Optional[str] = None,
                        quality_profile_id: Optional[int] = None, monitor_seasons: str = "all", series_type: str = "Standard") -> Optional[Dict[str, Any]]:
        """Add a TV series to Sonarr with season monitoring.

        Args:
            series_id: TheTVDB series ID
            title: Series title
            root_folder_path: Root folder path for the series
            quality_profile_id: Quality profile ID
            monitor_seasons: Season monitoring type — a key of MONITOR_TYPES
            series_type: Series type - "Standard", "Daily", or "Anime" for absolute episode numbering

        Returns:
            Response from Sonarr API or None on error
        """
        if root_folder_path is None:
            # Anime lands in the anime root unless the caller says otherwise.
            root_folder_path = settings.sonarr_root_anime if series_type == "Anime" else settings.sonarr_root_shows
        if quality_profile_id is None:
            quality_profile_id = settings.quality_profile_id

        url = f"{self.base_url}/api/v3/series"

        monitor = self.MONITOR_TYPES.get(monitor_seasons, "all")
        search = self.SEARCH_ON_ADD.get(monitor_seasons, True)

        payload = {
            "tvdbId": series_id,
            "title": title,
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "seriesType": series_type,
            "monitored": monitor_seasons != "none",
            "seasonFolder": True,
            "addOptions": {
                "monitor": monitor,
                "searchForMissingEpisodes": search,
                "searchForCutoffUnmetEpisodes": False,
            },
        }

        try:
            async with self._session_ctx() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    else:
                        error_text = await resp.text()
                        logger.error(f"Sonarr add series error: {resp.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Sonarr add series failed: {e}")
            return None
    
    async def get_monitored_series(self) -> Optional[List[Dict[str, Any]]]:
        """Get every series in the library.

        Returns:
            The library (possibly empty), or None if Sonarr couldn't be reached —
            callers must not report an outage as "nothing in the library".
        """
        status, body = await self._request("GET", "/api/v3/series")
        if status == 200:
            return body
        logger.error(f"Sonarr get series error: {status} - {body}")
        return None
    
    async def trigger_series_search(self, series_id: int) -> bool:
        """Trigger an immediate search for a specific series.
        
        Args:
            series_id: Series ID to search for
            
        Returns:
            True if search was triggered, False on error
        """
        url = f"{self.base_url}/api/v3/command"
        
        payload = {
            "name": "SeriesSearch",
            "seriesId": series_id
        }
        
        try:
            async with self._session_ctx() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"Triggered search for series {series_id}")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Sonarr trigger search error: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Sonarr trigger search failed: {e}")
            return False
    
    async def trigger_monitored_search(self) -> bool:
        """Trigger search for missing episodes in all monitored series (Search Monitored button).
        
        Returns:
            True if search was triggered, False on error
        """
        url = f"{self.base_url}/api/v3/command"
        
        payload = {
            "name": "MissingEpisodeSearch"
        }
        
        try:
            async with self._session_ctx() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        logger.info("Triggered search for missing episodes in all monitored series")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Sonarr trigger monitored search error: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Sonarr trigger monitored search failed: {e}")
            return False

    async def get_root_folders(self) -> List[Dict[str, Any]]:
        """Get available root folders.

        Returns:
            List of root folders with id and path
        """
        url = f"{self.base_url}/api/v3/rootFolder"
        
        try:
            async with self._session_ctx() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Sonarr get root folders error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Sonarr get root folders failed: {e}")
            return []


    async def get_series(self, series_id: int) -> Optional[Dict[str, Any]]:
        """Get one library series by its Sonarr id, None if it isn't there (any more).

        Raises on any other failure, so an outage isn't mistaken for a deletion.
        """
        status, body = await self._request("GET", f"/api/v3/series/{series_id}")
        if status == 200:
            return body
        if status == 404:
            return None
        # Anything else (outage, auth, 5xx) must not read as "deleted" — callers
        # would tell the user it's gone and strip the panel's buttons.
        raise RuntimeError(f"Sonarr get series failed: {status} - {body}")

    async def update_series(self, series: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PUT a full series resource back, as Sonarr's own UI does. Files are never moved.

        Changing a season's "monitored" here also flips every episode in that
        season to match — Sonarr does that server-side, same as the season toggle
        on the series page.
        """
        status, body = await self._request(
            "PUT", f"/api/v3/series/{series['id']}", json=series, params={"moveFiles": "false"}
        )
        if status in (200, 202):
            return body
        logger.error(f"Sonarr update series error: {status} - {body}")
        return None

    async def delete_series(self, series_id: int, delete_files: bool) -> bool:
        """Remove a series from Sonarr, optionally deleting its folder from disk.

        Mirrors the web UI's delete dialog with "Add List Exclusion" left unticked.
        aiohttp rejects bools in query params, hence the strings.
        """
        params = {
            "deleteFiles": "true" if delete_files else "false",
            "addImportListExclusion": "false",
        }
        status, body = await self._request("DELETE", f"/api/v3/series/{series_id}", params=params)
        if status in (200, 204):
            logger.info(f"Deleted series {series_id} (deleteFiles={delete_files})")
            return True
        logger.error(f"Sonarr delete series error: {status} - {body}")
        return False
