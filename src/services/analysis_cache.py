# Minimal TTL cache for base analysis artifacts
import json
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from src.data_models.analysis_schemas import BaseAnalysisArtifact

logger = logging.getLogger(__name__)

class AnalysisCache:
    """Simple TTL cache for base analysis artifacts"""
    
    def __init__(self, ttl_hours: int = 3, redis_client=None):
        self.ttl_hours = ttl_hours
        self.redis_client = redis_client
        # In-memory fallback cache
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
    
    async def get_cached_analysis(self, proposal_id: str, dao_id: str, source: str) -> Optional[BaseAnalysisArtifact]:
        """Get cached base analysis if it exists and is fresh"""
        cache_key = self._build_cache_key(proposal_id, dao_id, source)
        
        try:
            # Try Redis first if available
            if self.redis_client:
                cached_data = await self._get_from_redis(cache_key)
                if cached_data:
                    return self._deserialize_artifact(cached_data)
            
            # Fallback to memory cache
            async with self._cache_lock:
                if cache_key in self._memory_cache:
                    cache_entry = self._memory_cache[cache_key]
                    if self._is_cache_fresh(cache_entry['stored_at']):
                        logger.info(f"Cache HIT (memory) for {cache_key}")
                        return BaseAnalysisArtifact(**cache_entry['data'])
                    else:
                        # Remove expired entry
                        del self._memory_cache[cache_key]
                        logger.info(f"Cache EXPIRED (memory) for {cache_key}")
            
            logger.info(f"Cache MISS for {cache_key}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving from cache {cache_key}: {e}")
            return None
    
    async def store_analysis(self, artifact: BaseAnalysisArtifact) -> bool:
        """Store base analysis artifact with TTL"""
        cache_key = artifact.to_cache_key()
        
        try:
            # Store in Redis if available
            if self.redis_client:
                success = await self._store_in_redis(cache_key, artifact)
                if success:
                    logger.info(f"Stored in Redis cache: {cache_key}")
                    return True
            
            # Store in memory cache
            async with self._cache_lock:
                self._memory_cache[cache_key] = {
                    'data': artifact.model_dump(),
                    'stored_at': datetime.now(timezone.utc)
                }
                logger.info(f"Stored in memory cache: {cache_key}")
                
                # Clean up expired entries periodically
                await self._cleanup_expired_memory_cache()
                
            return True
            
        except Exception as e:
            logger.error(f"Error storing to cache {cache_key}: {e}")
            return False
    
    async def invalidate_cache(self, proposal_id: str, dao_id: str, source: str) -> bool:
        """Manually invalidate cached analysis"""
        cache_key = self._build_cache_key(proposal_id, dao_id, source)
        
        try:
            # Remove from Redis if available
            if self.redis_client:
                await self.redis_client.delete(cache_key)
            
            # Remove from memory cache
            async with self._cache_lock:
                if cache_key in self._memory_cache:
                    del self._memory_cache[cache_key]
                    
            logger.info(f"Invalidated cache: {cache_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating cache {cache_key}: {e}")
            return False
    
    def _build_cache_key(self, proposal_id: str, dao_id: str, source: str) -> str:
        """Build cache key from proposal identifiers"""
        return f"base_analysis:{source}:{dao_id}:{proposal_id}"
    
    def _is_cache_fresh(self, stored_at: datetime) -> bool:
        """Check if cached entry is still fresh"""
        expiry_time = stored_at + timedelta(hours=self.ttl_hours)
        return datetime.now(timezone.utc) < expiry_time
    
    async def _cleanup_expired_memory_cache(self):
        """Remove expired entries from memory cache"""
        try:
            current_time = datetime.now(timezone.utc)
            expired_keys = []
            
            for key, entry in self._memory_cache.items():
                if not self._is_cache_fresh(entry['stored_at']):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._memory_cache[key]
                
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
                
        except Exception as e:
            logger.error(f"Error cleaning up memory cache: {e}")
    
    async def _get_from_redis(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get data from Redis cache"""
        try:
            if hasattr(self.redis_client, 'get'):
                # Sync Redis client
                data = self.redis_client.get(cache_key)
            else:
                # Async Redis client
                data = await self.redis_client.get(cache_key)
                
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def _store_in_redis(self, cache_key: str, artifact: BaseAnalysisArtifact) -> bool:
        """Store data in Redis cache with TTL"""
        try:
            data = json.dumps(artifact.model_dump(), default=str)
            ttl_seconds = self.ttl_hours * 3600
            
            if hasattr(self.redis_client, 'setex'):
                # Sync Redis client
                self.redis_client.setex(cache_key, ttl_seconds, data)
            else:
                # Async Redis client
                await self.redis_client.setex(cache_key, ttl_seconds, data)
                
            return True
            
        except Exception as e:
            logger.error(f"Redis store error: {e}")
            return False
    
    def _deserialize_artifact(self, data: Dict[str, Any]) -> BaseAnalysisArtifact:
        """Deserialize cached data back to artifact"""
        # Handle datetime deserialization
        if isinstance(data.get('analyzed_at'), str):
            data['analyzed_at'] = datetime.fromisoformat(data['analyzed_at'].replace('Z', '+00:00'))
        
        return BaseAnalysisArtifact(**data)
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        async with self._cache_lock:
            memory_count = len(self._memory_cache)
            
        return {
            'memory_cache_entries': memory_count,
            'ttl_hours': self.ttl_hours,
            'redis_available': self.redis_client is not None
        }
