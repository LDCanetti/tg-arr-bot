import aiohttp
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from app.config.settings import settings

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
            async with self._session_ctx() as session:
                async with session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Radarr search error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Radarr search failed: {e}")
            return []
    
    async def add_movie(self, tmdb_id: int, root_folder_path: Optional[str] = None,
                       quality_profile_id: Optional[int] = None, monitor: bool = True) -> Optional[Dict[str, Any]]:
        """Add a movie to Radarr.

        Args:
            tmdb_id: The Movie Database (TMDb) ID
            root_folder_path: Root folder path for the movie
            quality_profile_id: Quality profile ID (defaults to the configured one)
            monitor: Whether to monitor the movie

        Returns:
            Response from Radarr API or None on error
        """
        if root_folder_path is None:
            root_folder_path = settings.radarr_root_movies
        if quality_profile_id is None:
            quality_profile_id = settings.quality_profile_id

        url = f"{self.base_url}/api/v3/movie"
        
        payload = {
            "title": "",  # Title will be filled by Radarr
            "tmdbId": tmdb_id,
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "monitored": monitor,
            # searchForMovie belongs inside addOptions. At the top level Radarr
            # drops it as an unknown property, still returns 201, and the movie
            # sits there unsearched until someone clicks Search by hand.
            "addOptions": {
                "searchForMovie": monitor,
            },
        }
        
        try:
            async with self._session_ctx() as session:
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
            async with self._session_ctx() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Radarr get movies error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Radarr get movies failed: {e}")
            return []
    
    async def trigger_movie_search(self, movie_id: int) -> bool:
        """Trigger an immediate search for a specific movie.
        
        Args:
            movie_id: Movie ID to search for
            
        Returns:
            True if search was triggered, False on error
        """
        url = f"{self.base_url}/api/v3/command"
        
        payload = {
            "name": "MoviesSearch",
            "movieIds": [movie_id]
        }
        
        try:
            async with self._session_ctx() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"Triggered search for movie {movie_id}")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Radarr trigger search error: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Radarr trigger search failed: {e}")
            return False
    
    async def trigger_monitored_search(self) -> bool:
        """Trigger search for missing movies in all monitored entries (Search Missing button).
        
        Returns:
            True if search was triggered, False on error
        """
        url = f"{self.base_url}/api/v3/command"
        
        payload = {
            "name": "MissingMoviesSearch"
        }
        
        try:
            async with self._session_ctx() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        logger.info("Triggered search for missing movies in all monitored entries")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Radarr trigger monitored search error: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Radarr trigger monitored search failed: {e}")
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
                        logger.error(f"Radarr get root folders error: {resp.status}")
                        return []
        except Exception as e:
            logger.error(f"Radarr get root folders failed: {e}")
            return []
