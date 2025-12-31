"""
Query caching implementation for GraphQL Query Optimizer.

Provides in-memory caching with TTL (Time To Live) support
and LRU (Least Recently Used) eviction policy.
"""

from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timedelta
from threading import Lock
import logging

from .utils import generate_cache_key

logger = logging.getLogger(__name__)


class QueryCache:
    """
    Thread-safe in-memory cache for query results.
    
    Features:
        - TTL (Time To Live) support
        - Max size limit with LRU eviction
        - Thread-safe operations
        - Model-based invalidation
    
    Usage:
        >>> cache = QueryCache(ttl_seconds=60, max_size=1000)
        >>> 
        >>> # Check cache
        >>> result = cache.get(cache_key)
        >>> if result is None:
        >>>     result = db_query()
        >>>     cache.set(cache_key, result)
        
    Example with decorator:
        >>> @cache.cached(ttl=30)
        >>> def get_orders(limit: int):
        >>>     return session.query(Order).limit(limit).all()
    """
    
    def __init__(
        self,
        ttl_seconds: int = 60,
        max_size: int = 1000,
        enable_stats: bool = True
    ):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Default cache entry lifetime (default: 60 seconds)
            max_size: Maximum number of cache entries (default: 1000)
            enable_stats: Track hit/miss statistics (default: True)
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.enable_stats = enable_stats
        
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        self._lock = Lock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if exists and not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                if self.enable_stats:
                    self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            if datetime.now() > entry["expires_at"]:
                self._remove_key(key)
                if self.enable_stats:
                    self._misses += 1
                return None
            
            # Update access order (LRU)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            
            if self.enable_stats:
                self._hits += 1
            
            return entry["value"]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override in seconds
        """
        with self._lock:
            # Evict if max size reached (LRU)
            while len(self._cache) >= self.max_size:
                if self._access_order:
                    oldest_key = self._access_order.pop(0)
                    self._cache.pop(oldest_key, None)
                else:
                    break
            
            actual_ttl = ttl if ttl is not None else self.ttl_seconds
            
            self._cache[key] = {
                "value": value,
                "expires_at": datetime.now() + timedelta(seconds=actual_ttl),
                "created_at": datetime.now()
            }
            
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
    
    def _remove_key(self, key: str) -> None:
        """Remove key from cache (internal, no lock)."""
        self._cache.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)
    
    def invalidate(self, key: str) -> bool:
        """
        Remove specific key from cache.
        
        Args:
            key: Cache key to invalidate
            
        Returns:
            True if key was found and removed
        """
        with self._lock:
            if key in self._cache:
                self._remove_key(key)
                return True
            return False
    
    def invalidate_model(self, model: Type) -> int:
        """
        Remove all cache entries for a specific model.
        
        Args:
            model: SQLAlchemy model class
            
        Returns:
            Number of entries invalidated
        """
        table_name = getattr(model, '__tablename__', str(model))
        
        with self._lock:
            keys_to_remove = [
                k for k in self._cache.keys() 
                if table_name in k
            ]
            
            for key in keys_to_remove:
                self._remove_key(key)
            
            return len(keys_to_remove)
    
    def invalidate_pattern(self, pattern: str) -> int:
        """
        Remove cache entries matching a pattern.
        
        Args:
            pattern: Substring to match in cache keys
            
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            keys_to_remove = [
                k for k in self._cache.keys() 
                if pattern in k
            ]
            
            for key in keys_to_remove:
                self._remove_key(key)
            
            return len(keys_to_remove)
    
    def clear(self) -> int:
        """
        Clear entire cache.
        
        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_order.clear()
            return count
    
    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "total_requests": total_requests
            }
    
    def reset_stats(self) -> None:
        """Reset hit/miss statistics."""
        with self._lock:
            self._hits = 0
            self._misses = 0
    
    def keys(self) -> List[str]:
        """Get all cache keys."""
        with self._lock:
            return list(self._cache.keys())
    
    def __len__(self) -> int:
        """Get number of cached entries."""
        return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache (without updating access time)."""
        return key in self._cache


# Global cache instance
_global_cache: Optional[QueryCache] = None


def get_cache(
    ttl_seconds: int = 60,
    max_size: int = 1000
) -> QueryCache:
    """
    Get or create global cache instance.
    
    Args:
        ttl_seconds: Default TTL for cache entries
        max_size: Maximum cache size
        
    Returns:
        Global QueryCache instance
    """
    global _global_cache
    
    if _global_cache is None:
        _global_cache = QueryCache(ttl_seconds=ttl_seconds, max_size=max_size)
    
    return _global_cache


def clear_cache() -> int:
    """
    Clear global cache.
    
    Returns:
        Number of entries cleared
    """
    global _global_cache
    
    if _global_cache is not None:
        return _global_cache.clear()
    return 0


def configure_cache(
    ttl_seconds: int = 60,
    max_size: int = 1000,
    enable_stats: bool = True
) -> QueryCache:
    """
    Configure and replace global cache instance.
    
    Args:
        ttl_seconds: Default TTL for cache entries
        max_size: Maximum cache size
        enable_stats: Enable hit/miss statistics
        
    Returns:
        New global QueryCache instance
    """
    global _global_cache
    
    _global_cache = QueryCache(
        ttl_seconds=ttl_seconds,
        max_size=max_size,
        enable_stats=enable_stats
    )
    
    return _global_cache
