#! /usr/bin/env python3
## File: cache.py
"""
LRU caching layer for database queries with TTL support
Provides efficient caching for frequently accessed data.
"""
import time
import json
from typing import Dict, Optional, Any
from collections import OrderedDict

from app.config import CONFIG
from app.utils.log_settings import setup_logging

logger = setup_logging('cache.log')

class SupabaseCache:
    """LRU cache implementation with TTL support"""

    def __init__(self, max_size: Optional[int] = None, ttl: Optional[int] = None):
        self._cache = OrderedDict()
        self._max_size = max_size or CONFIG.monitoring.cache_max_size
        self._ttl = ttl or CONFIG.monitoring.cache_ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get cached item if valid and not expired"""
        if key not in self._cache:
            self._misses += 1
            return None
        
        item = self._cache[key]

        # Check if item has expired
        if time.time() - item['timestamp'] > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        
        # Move to end to mark as recently used
        self._cache.move_to_end(key)
        self._hits += 1
        logger.debug(f"Cache hit for key: {key}")
        return item['data']
    
    def set(self, key: str, data: Any) -> None:
        """Cache an item with LRU eviction if needed"""
        # Remove oldest item if cache is full (Fixed typo)
        while len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Evicted cache key: {oldest_key}")
        
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }

    def delete(self, key: str) -> bool:
        """Delete a specific cache entry"""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Deleted cache key: {key}")
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Cache cleared")
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern"""
        keys_to_delete = [key for key in self._cache.keys() if pattern in key]
        for key in keys_to_delete:
            del self._cache[key]
        
        logger.debug(f"Invalidated {len(keys_to_delete)} cache entries matching pattern: {pattern}")
        return len(keys_to_delete)
    
    def cleanup_expired(self) -> int:
        """Remove expired entries from cache"""
        current_time = time.time()
        expired_keys = [
            key for key, item in self._cache.items()
            if current_time - item['timestamp'] > self._ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self._cache),
            'max_size': self._max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': round(hit_rate, 2),
            'ttl': self._ttl
        }
    
    @staticmethod
    def make_cache_key(method: str, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate a consistent cache key for database requests"""
        key_parts = [method.upper(), endpoint]

        if params:
            try:
                sorted_params = json.dumps(params, sort_keys=True)
                key_parts.append(sorted_params)
            except TypeError as e:
                logger.warning(f"Non-serializable params in cache key generation: {e}")
                # Fallback to string representation
                sorted_params = str(sorted(params.items()))
                key_parts.append(sorted_params)
        
        return ':'.join(key_parts)

class CachedSupabaseHandler:
    """Supabase handler with caching capabilities"""

    def __init__(self, handler, cache: Optional[SupabaseCache] = None):
        self.handler = handler
        self.cache = cache or SupabaseCache()
    
    async def make_request(self, method: str, endpoint: str, 
                         data: Optional[Dict] = None, 
                         params: Optional[Dict] = None,
                         use_cache: bool = True) -> tuple[Optional[Dict], Optional[str]]:
        """Make request with caching support"""
        # Only cache GET requests
        if use_cache and method.upper() == 'GET' and not data:
            cache_key = SupabaseCache.make_cache_key(method, endpoint, params)

            # Try to get from cache first
            cached_results = self.cache.get(cache_key)
            if cached_results is not None:
                return cached_results, None
        
        # Make actual request
        result, error = await self.handler.make_request(method, endpoint, data, params)

        # Cache successful GET requests
        if (use_cache and method.upper() == 'GET' and not data and
            error is None and result is not None):
            cache_key = SupabaseCache.make_cache_key(method, endpoint, params)
            self.cache.set(cache_key, result)
        
        return result, error
    
    def invalidate_table_cache(self, table: str) -> int:
        """Invalidate all cache entries for a specific table"""
        return self.cache.invalidate_pattern(table)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.cache.get_stats()
    
    async def close(self) -> None:
        """Close handler and cleanup"""
        await self.handler.close()
    
    # Delegate methods to the underlying handler
    async def get_records(self, table: str, **filters):
        """Get records from a table with optional filters"""
        return await self.handler.get_records(table, **filters)
    
    async def search_brv_number(self, brv_number: str):
        """Search for records by BRV number across all tables"""
        return await self.handler.search_brv_number(brv_number)

    async def get_table_stats(self):
        """Get record counts for all tables"""
        return await self.handler.get_table_stats()

    async def get_total_volume_loaded(self):
        """Get the total volume for specified tables"""
        return await self.handler.get_total_volume_loaded()

    async def get_new_records(self, table_name: str):
        """Fetch recent records from a specified table"""
        return await self.handler.get_new_records(table_name)

    async def insert_record(self, table: str, data: Dict):
        """Insert a record into a table"""
        # Invalidate cache for this table after insert
        self.invalidate_table_cache(table)
        return await self.handler.insert_record(table, data)
    
    async def update_record(self, table: str, record_id: int, data: Dict):
        """Update a record in a table"""
        # Invalidate cache for this table after update
        self.invalidate_table_cache(table)
        return await self.handler.update_record(table, record_id, data)
    
    async def delete_record(self, table: str, record_id: int):
        """Delete a record from a table"""
        # Invalidate cache for this table after delete
        self.invalidate_table_cache(table)
        return await self.handler.delete_record(table, record_id)