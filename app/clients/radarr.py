import aiohttp
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class RadarrClient:
    """Radarr API client for movie management."""
    
    def __init__(self, base_url: str, api_key: str):
        """Initialize Radarr client.
        
        Args:
            base_url: Base URL of Radarr instance (e.g., http://radarr:7878)
            api_key: Radarr API key
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"X-Api-Key": api_key}
    
    async def search_movies(self, query: str) -> List[Dict[str, Any]]:
        """Search for movies by title.
        
        Args:
            query: Movie title to search for
            
        Returns:
            List of matching movies
        """
        url = f"{self.base_url}/api/v3/movie/lookup"
        params = {"term": query}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Radarr search error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Radarr search failed: {e}")
            return []
    
    async def add_movie(self, tmdb_id: int, root_folder_path: str = "/Movies",
                       quality_profile_id: int = 1, monitor: bool = True) -> Optional[Dict[str, Any]]:
        """Add a movie to Radarr.
        
        Args:
            tmdb_id: The Movie Database (TMDb) ID
            root_folder_path: Root folder path for the movie
            quality_profile_id: Quality profile ID
            monitor: Whether to monitor the movie
            
        Returns:
            Response from Radarr API or None on error
        """
        url = f"{self.base_url}/api/v3/movie"
        
        payload = {
            "title": "",  # Title will be filled by Radarr
            "tmdbId": tmdb_id,
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "monitored": monitor,
            "searchForMovie": True,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    else:
                        error_text = await resp.text()
                        logger.error(f"Radarr add movie error: {resp.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Radarr add movie failed: {e}")
            return None
    
    async def get_monitored_movies(self) -> List[Dict[str, Any]]:
        """Get list of monitored movies.
        
        Returns:
            List of monitored movies
        """
        url = f"{self.base_url}/api/v3/movie"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Radarr get movies error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Radarr get movies failed: {e}")
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
                        logger.error(f"Radarr get root folders error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Radarr get root folders failed: {e}")
            return []
