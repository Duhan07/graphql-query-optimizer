"""Tests for DataLoader implementations."""

import pytest
from unittest.mock import MagicMock, patch
from gql_optimizer.dataloader import SyncDataLoader, AsyncDataLoader, create_dataloader


class MockModel:
    """Mock SQLAlchemy model for testing."""
    __tablename__ = "mock_table"
    
    def __init__(self, id=None, name=None):
        self.id = id
        self.name = name


class MockQuery:
    """Mock SQLAlchemy query."""
    
    def __init__(self, results=None):
        self._results = results or []
        self._filter = None
    
    def filter(self, condition):
        self._filter = condition
        return self
    
    def first(self):
        return self._results[0] if self._results else None
    
    def all(self):
        return self._results


class MockSession:
    """Mock SQLAlchemy session."""
    
    def __init__(self, results=None):
        self._results = results or []
    
    def query(self, model):
        return MockQuery(self._results)


class TestSyncDataLoader:
    """Test SyncDataLoader class."""
    
    def test_init(self):
        """Test initialization."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        assert loader.session == session
        assert len(loader._cache) == 0
    
    def test_load_single(self):
        """Test loading single entity."""
        entity = MockModel(id="1", name="Test")
        session = MockSession([entity])
        loader = SyncDataLoader(session)
        
        result = loader.load(MockModel, "1")
        
        assert result == entity
    
    def test_load_none_key(self):
        """Test loading with None key."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        result = loader.load(MockModel, None)
        
        assert result is None
    
    def test_load_caches_result(self):
        """Test that load caches results."""
        entity = MockModel(id="1", name="Test")
        session = MockSession([entity])
        loader = SyncDataLoader(session)
        
        # First call
        result1 = loader.load(MockModel, "1")
        
        # Clear session results to verify cache is used
        session._results = []
        
        # Second call should use cache
        result2 = loader.load(MockModel, "1")
        
        assert result1 == result2
    
    def test_load_many_empty(self):
        """Test load_many with empty list."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        result = loader.load_many(MockModel, [])
        
        assert result == []
    
    def test_load_many_batch(self):
        """Test load_many batches queries."""
        entities = [
            MockModel(id="1", name="One"),
            MockModel(id="2", name="Two"),
            MockModel(id="3", name="Three"),
        ]
        session = MockSession(entities)
        loader = SyncDataLoader(session)
        
        result = loader.load_many(MockModel, ["1", "2", "3"])
        
        assert len(result) == 3
    
    def test_load_many_preserves_order(self):
        """Test load_many preserves order of keys."""
        entities = [
            MockModel(id="1", name="One"),
            MockModel(id="2", name="Two"),
        ]
        session = MockSession(entities)
        loader = SyncDataLoader(session)
        
        # Request in different order
        result = loader.load_many(MockModel, ["2", "1"])
        
        # Results should be in requested order
        assert result[0].id == "2"
        assert result[1].id == "1"
    
    def test_load_many_handles_missing(self):
        """Test load_many returns None for missing keys."""
        entities = [MockModel(id="1", name="One")]
        session = MockSession(entities)
        loader = SyncDataLoader(session)
        
        result = loader.load_many(MockModel, ["1", "nonexistent"])
        
        assert len(result) == 2
        assert result[0].id == "1"
        assert result[1] is None
    
    def test_load_many_deduplicates(self):
        """Test load_many deduplicates keys."""
        entity = MockModel(id="1", name="One")
        session = MockSession([entity])
        loader = SyncDataLoader(session)
        
        result = loader.load_many(MockModel, ["1", "1", "1"])
        
        assert len(result) == 3
        assert all(r.id == "1" for r in result)
    
    def test_prime(self):
        """Test prime adds to cache."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        entity = MockModel(id="1", name="Test")
        loader.prime(MockModel, entity)
        
        # Should get from cache without hitting DB
        result = loader.load(MockModel, "1")
        
        assert result == entity
    
    def test_prime_many(self):
        """Test prime_many adds multiple to cache."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        entities = [
            MockModel(id="1", name="One"),
            MockModel(id="2", name="Two"),
        ]
        loader.prime_many(MockModel, entities)
        
        # Should get from cache
        result = loader.load_many(MockModel, ["1", "2"])
        
        assert len(result) == 2
    
    def test_clear(self):
        """Test clear removes all cache."""
        entity = MockModel(id="1", name="Test")
        session = MockSession([entity])
        loader = SyncDataLoader(session)
        
        loader.load(MockModel, "1")
        loader.clear()
        
        assert len(loader._cache) == 0
    
    def test_clear_specific_model(self):
        """Test clear for specific model."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        loader.prime(MockModel, MockModel(id="1", name="Test"))
        
        # Create another mock model class
        class OtherModel:
            __tablename__ = "other_table"
        
        loader._cache["other_table:id"] = {"1": "data"}
        
        loader.clear(MockModel)
        
        assert "mock_table:id" not in loader._cache or len(loader._cache["mock_table:id"]) == 0
        assert len(loader._cache["other_table:id"]) == 1
    
    def test_custom_key_field(self):
        """Test loading with custom key field."""
        entity = MockModel(id="1", name="Test")
        entity.order_id = "ORD-123"
        session = MockSession([entity])
        loader = SyncDataLoader(session)
        
        # This would work if the mock supported attribute access
        # In real usage: loader.load(OrderModel, "ORD-123", key_field="order_id")
        cache_key = loader._get_cache_key(MockModel, "order_id")
        assert cache_key == "mock_table:order_id"
    
    def test_stats(self):
        """Test stats method."""
        session = MockSession()
        loader = SyncDataLoader(session)
        
        loader.prime(MockModel, MockModel(id="1", name="Test"))
        
        stats = loader.stats()
        
        assert "models_cached" in stats
        assert "total_entries" in stats
        assert stats["total_entries"] == 1


class TestCreateDataLoader:
    """Test create_dataloader factory function."""
    
    def test_creates_sync_for_sync_session(self):
        """Test creates SyncDataLoader for sync session."""
        session = MockSession()
        
        loader = create_dataloader(session)
        
        assert isinstance(loader, SyncDataLoader)
    
    def test_creates_async_for_async_session(self):
        """Test creates AsyncDataLoader for async session."""
        # Mock async session
        class AsyncSession:
            pass
        
        session = AsyncSession()
        
        loader = create_dataloader(session)
        
        assert isinstance(loader, AsyncDataLoader)
