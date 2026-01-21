import aiohttp
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class SonarrClient:
    """Sonarr API client for TV series management."""
    
    def __init__(self, base_url: str, api_key: str):
        """Initialize Sonarr client.
        
        Args:
            base_url: Base URL of Sonarr instance (e.g., http://sonarr:8989)
            api_key: Sonarr API key
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}
    
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
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Sonarr search error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Sonarr search failed: {e}")
            return []
    
    async def add_series(self, series_id: int, title: str = "", root_folder_path: str = "/Shows", 
                        quality_profile_id: int = 1, monitor_seasons: str = "all", series_type: str = "Standard") -> Optional[Dict[str, Any]]:
        """Add a TV series to Sonarr with season monitoring.
        
        Args:
            series_id: TheTVDB series ID
            title: Series title
            root_folder_path: Root folder path for the series
            quality_profile_id: Quality profile ID
            monitor_seasons: Season monitoring type (all, first, last, none, future, missing, existing, recent, pilot)
            series_type: Series type - "Standard", "Daily", or "Anime" for absolute episode numbering
            
        Returns:
            Response from Sonarr API or None on error
        """
        url = f"{self.base_url}/api/v3/series"
        
        # Map monitor_seasons to the proper addOptions structure
        # Sonarr uses searchForMissingEpisodes to determine what to download
        add_options_mapping = {
            "all": {"searchForMissingEpisodes": True},
            "future": {"searchForMissingEpisodes": False},  # Only new episodes
            "missing": {"searchForMissingEpisodes": True},   # Search for missing
            "existing": {"searchForMissingEpisodes": False}, # Only existing
            "recent": {"searchForMissingEpisodes": True},    # Recent episodes
            "pilot": {"searchForMissingEpisodes": True},     # Pilot episode
            "first": {"searchForMissingEpisodes": True},     # First season
            "last": {"searchForMissingEpisodes": False},     # Last season - don't search old episodes
            "specials": {"searchForMissingEpisodes": True},  # Specials
            "no_specials": {"searchForMissingEpisodes": True},
            "none": {"searchForMissingEpisodes": False}
        }
        
        # Determine monitored status
        monitored = monitor_seasons != "none"
        
        # Get add options for this monitor type
        add_options = add_options_mapping.get(monitor_seasons, {"searchForMissingEpisodes": True})
        
        payload = {
            "tvdbId": series_id,
            "title": title,
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "seriesType": series_type,
            "monitored": monitored,
            "seasonFolder": True,
            "addOptions": add_options
        }
        
        # For "first" season only - we need to unmonitor other seasons after adding
        if monitor_seasons == "first":
            payload["seasons"] = [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": -1, "monitored": False}  # Specials unmonitored
            ]
        # For "last" season only - get all seasons and mark all but last as unmonitored
        elif monitor_seasons == "last":
            # Search for series to get season information
            search_url = f"{self.base_url}/api/v3/series/lookup"
            search_params = {"term": f"tvdb:{series_id}"}
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(search_url, headers=self.headers, params=search_params) as resp:
                        if resp.status == 200:
                            search_results = await resp.json()
                            if search_results:
                                series_info = search_results[0]
                                seasons = series_info.get("seasons", [])
                                if seasons:
                                    max_season = max([s.get("seasonNumber", 0) for s in seasons])
                                    payload["seasons"] = [
                                        {"seasonNumber": s.get("seasonNumber", 0), 
                                         "monitored": s.get("seasonNumber", 0) == max_season or s.get("seasonNumber", 0) == 0}
                                        for s in seasons
                                    ]
            except Exception as e:
                logger.warning(f"Failed to get season info for 'last' option: {e}")
                # Continue with default - Sonarr will handle it
        elif monitor_seasons == "none":
            payload["monitored"] = False
        
        try:
            async with aiohttp.ClientSession() as session:
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
    
    async def get_monitored_series(self) -> List[Dict[str, Any]]:
        """Get list of monitored TV series.
        
        Returns:
            List of monitored series
        """
        url = f"{self.base_url}/api/v3/series"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Sonarr get series error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Sonarr get series failed: {e}")
            return []
    
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
            async with aiohttp.ClientSession() as session:
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
            async with aiohttp.ClientSession() as session:
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
        """Get available root folders.
        
        Returns:
            List of root folders with id and path
        """
        url = f"{self.base_url}/api/v3/rootFolder"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Sonarr get root folders error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Sonarr get root folders failed: {e}")
            return []
