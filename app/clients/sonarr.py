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
    
    async def add_series(self, series_id: int, root_folder_path: str = "/tv", 
                        quality_profile_id: int = 1, monitor_type: str = "all") -> Optional[Dict[str, Any]]:
        """Add a TV series to Sonarr.
        
        Args:
            series_id: TheTVDB series ID
            root_folder_path: Root folder path for the series
            quality_profile_id: Quality profile ID
            monitor_type: Monitor type (all, future, missing, existing, pilot, unmonitored)
            
        Returns:
            Response from Sonarr API or None on error
        """
        url = f"{self.base_url}/api/v3/series"
        
        payload = {
            "tvdbId": series_id,
            "title": "",  # Title will be filled by Sonarr
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "monitored": True,
            "monitorNewItems": "all",
            "seasonFolder": True,
        }
        
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
    
    async def get_root_folders(self) -> List[Dict[str, Any]]:
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
