import logging
from typing import Optional, List, Dict, Any

from app.clients.base import ArrClient
from app.config.settings import settings

logger = logging.getLogger(__name__)


class RadarrClient(ArrClient):
    """Radarr API client for movie management."""

    service = "Radarr"
    QUEUE_INCLUDES = {"includeMovie": "true", "includeUnknownMovieItems": "true"}

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
    
    async def get_monitored_movies(self) -> Optional[List[Dict[str, Any]]]:
        """Get every movie in the library.

        Returns:
            The library (possibly empty), or None if Radarr couldn't be reached —
            callers must not report an outage as "nothing in the library".
        """
        status, body = await self._request("GET", "/api/v3/movie")
        if status == 200:
            return body
        logger.error(f"Radarr get movies error: {status} - {body}")
        return None
    
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


    async def get_movie(self, movie_id: int) -> Optional[Dict[str, Any]]:
        """Get one library movie by its Radarr id, None if it isn't there (any more).

        Raises on any other failure, so an outage isn't mistaken for a deletion.
        """
        status, body = await self._request("GET", f"/api/v3/movie/{movie_id}")
        if status == 200:
            return body
        if status == 404:
            return None
        # Anything else (outage, auth, 5xx) must not read as "deleted" — callers
        # would tell the user it's gone and strip the panel's buttons.
        raise RuntimeError(f"Radarr get movie failed: {status} - {body}")

    async def update_movie(self, movie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PUT a full movie resource back, as Radarr's edit dialog does. Files are never moved."""
        status, body = await self._request(
            "PUT", f"/api/v3/movie/{movie['id']}", json=movie, params={"moveFiles": "false"}
        )
        if status in (200, 202):
            return body
        logger.error(f"Radarr update movie error: {status} - {body}")
        return None

    async def delete_movie(self, movie_id: int, delete_files: bool) -> bool:
        """Remove a movie from Radarr, optionally deleting its folder from disk.

        Mirrors the web UI's delete dialog with "Add List Exclusion" left unticked.
        aiohttp rejects bools in query params, hence the strings.
        """
        params = {
            "deleteFiles": "true" if delete_files else "false",
            "addImportExclusion": "false",
        }
        status, body = await self._request("DELETE", f"/api/v3/movie/{movie_id}", params=params)
        if status in (200, 204):
            logger.info(f"Deleted movie {movie_id} (deleteFiles={delete_files})")
            return True
        logger.error(f"Radarr delete movie error: {status} - {body}")
        return False
