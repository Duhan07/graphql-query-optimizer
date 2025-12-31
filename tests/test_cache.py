"""Tests for QueryCache."""

import pytest
import time
from gql_optimizer.cache import QueryCache, get_cache, clear_cache, configure_cache


class TestQueryCache:
    """Test QueryCache class."""
    
    def test_init_defaults(self):
        """Test default initialization."""
        cache = QueryCache()
        assert cache.ttl_seconds == 60
        assert cache.max_size == 1000
        assert len(cache) == 0
    
    def test_init_custom(self):
        """Test custom initialization."""
        cache = QueryCache(ttl_seconds=30, max_size=500)
        assert cache.ttl_seconds == 30
        assert cache.max_size == 500
    
    def test_set_and_get(self):
        """Test basic set and get."""
        cache = QueryCache()
        
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_get_nonexistent(self):
        """Test get for nonexistent key."""
        cache = QueryCache()
        assert cache.get("nonexistent") is None
    
    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = QueryCache(ttl_seconds=1)
        
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        # Wait for expiration
        time.sleep(1.1)
        
        assert cache.get("key1") is None
    
    def test_custom_ttl_on_set(self):
        """Test custom TTL on individual set."""
        cache = QueryCache(ttl_seconds=60)
        
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"
        
        time.sleep(1.1)
        assert cache.get("key1") is None
    
    def test_max_size_eviction(self):
        """Test LRU eviction when max size reached."""
        cache = QueryCache(max_size=3)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        assert len(cache) == 3
        
        # This should evict key1 (oldest)
        cache.set("key4", "value4")
        
        assert len(cache) == 3
        assert cache.get("key1") is None
        assert cache.get("key4") == "value4"
    
    def test_lru_order_updated_on_get(self):
        """Test that get updates LRU order."""
        cache = QueryCache(max_size=3)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        # Access key1, making it most recently used
        cache.get("key1")
        
        # Add new key, should evict key2 (now oldest)
        cache.set("key4", "value4")
        
        assert cache.get("key1") == "value1"  # Still exists
        assert cache.get("key2") is None      # Evicted
    
    def test_invalidate(self):
        """Test invalidate specific key."""
        cache = QueryCache()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        result = cache.invalidate("key1")
        
        assert result is True
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
    
    def test_invalidate_nonexistent(self):
        """Test invalidate nonexistent key."""
        cache = QueryCache()
        result = cache.invalidate("nonexistent")
        assert result is False
    
    def test_invalidate_pattern(self):
        """Test invalidate by pattern."""
        cache = QueryCache()
        
        cache.set("order:1", "o1")
        cache.set("order:2", "o2")
        cache.set("user:1", "u1")
        
        count = cache.invalidate_pattern("order")
        
        assert count == 2
        assert cache.get("order:1") is None
        assert cache.get("order:2") is None
        assert cache.get("user:1") == "u1"
    
    def test_clear(self):
        """Test clear all cache."""
        cache = QueryCache()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        count = cache.clear()
        
        assert count == 2
        assert len(cache) == 0
    
    def test_stats(self):
        """Test cache statistics."""
        cache = QueryCache(ttl_seconds=60, max_size=1000)
        
        # Generate some hits and misses
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.stats()
        
        assert stats["size"] == 1
        assert stats["max_size"] == 1000
        assert stats["ttl_seconds"] == 60
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(66.67, rel=0.1)
    
    def test_contains(self):
        """Test __contains__ method."""
        cache = QueryCache()
        
        cache.set("key1", "value1")
        
        assert "key1" in cache
        assert "key2" not in cache
    
    def test_keys(self):
        """Test keys method."""
        cache = QueryCache()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        keys = cache.keys()
        
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys


class TestGlobalCache:
    """Test global cache functions."""
    
    def test_get_cache(self):
        """Test get_cache returns singleton."""
        cache1 = get_cache()
        cache2 = get_cache()
        
        # Should be same instance
        cache1.set("test", "value")
        assert cache2.get("test") == "value"
    
    def test_clear_cache(self):
        """Test clear_cache function."""
        cache = get_cache()
        cache.set("test", "value")
        
        clear_cache()
        
        assert cache.get("test") is None
    
    def test_configure_cache(self):
        """Test configure_cache creates new instance."""
        configure_cache(ttl_seconds=30, max_size=100)
        
        cache = get_cache()
        assert cache.ttl_seconds == 30
        assert cache.max_size == 100
        
        # Reset to defaults
        configure_cache(ttl_seconds=60, max_size=1000)
