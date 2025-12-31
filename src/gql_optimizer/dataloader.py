"""
DataLoader implementations for batching database queries.

Solves the N+1 problem by batching multiple loads into single queries.
Provides both synchronous and asynchronous implementations.
"""

from typing import (
    Any, Callable, Dict, Generic, List, Optional, 
    Set, Type, TypeVar, Union, Sequence
)
from collections import defaultdict
import asyncio
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select

logger = logging.getLogger(__name__)

T = TypeVar('T')
K = TypeVar('K')


class SyncDataLoader(Generic[T, K]):
    """
    Synchronous DataLoader for batching database queries.
    
    Solves the N+1 problem by collecting multiple load requests
    and executing them in a single batch query.
    
    Features:
        - Batch loading
        - Per-request caching
        - Order preservation
        - Null handling for missing keys
        - Deduplication
    
    Usage:
        >>> loader = SyncDataLoader(session)
        >>> 
        >>> # Single load
        >>> courier = loader.load(CourierModel, "courier_123")
        >>> 
        >>> # Batch load
        >>> couriers = loader.load_many(CourierModel, ["c1", "c2", "c3"])
        >>> 
        >>> # Custom key field
        >>> order = loader.load(OrderModel, "ORD-123", key_field="order_id")
    
    Best Practices:
        - Create a new loader per request to avoid stale data
        - Use load_many for multiple IDs (more efficient)
        - Clear cache if data might have changed
    """
    
    def __init__(self, session: Session):
        """
        Initialize DataLoader.
        
        Args:
            session: SQLAlchemy session for database queries
        """
        self.session = session
        self._cache: Dict[str, Dict[Any, Any]] = defaultdict(dict)
    
    def _get_cache_key(self, model: Type[T], key_field: str) -> str:
        """Generate unique cache key for model+field combination."""
        return f"{model.__tablename__}:{key_field}"
    
    def load(
        self,
        model: Type[T],
        key_value: K,
        key_field: str = "id"
    ) -> Optional[T]:
        """
        Load a single entity by key.
        
        For single loads, this is not batched. Use load_many for
        batching multiple loads.
        
        Args:
            model: SQLAlchemy model class
            key_value: Value to search for
            key_field: Column name to search by (default: "id")
            
        Returns:
            Model instance or None if not found
        """
        if key_value is None:
            return None
        
        cache_key = self._get_cache_key(model, key_field)
        
        # Check cache
        if key_value in self._cache[cache_key]:
            return self._cache[cache_key][key_value]
        
        # Query database
        key_column = getattr(model, key_field)
        entity = self.session.query(model).filter(
            key_column == key_value
        ).first()
        
        # Cache result (even if None to avoid repeated queries)
        self._cache[cache_key][key_value] = entity
        
        return entity
    
    def load_many(
        self,
        model: Type[T],
        key_values: Sequence[K],
        key_field: str = "id"
    ) -> List[Optional[T]]:
        """
        Load multiple entities by keys in a single batch query.
        
        This is the main method for solving N+1 problems.
        Results are returned in the same order as input keys.
        
        Args:
            model: SQLAlchemy model class
            key_values: List of values to search for
            key_field: Column name to search by (default: "id")
            
        Returns:
            List of model instances (None for missing keys)
            
        Example:
            >>> ids = ["c1", "c2", "c3"]
            >>> couriers = loader.load_many(CourierModel, ids)
            >>> # Returns [Courier1, Courier2, None] if c3 doesn't exist
        """
        if not key_values:
            return []
        
        cache_key = self._get_cache_key(model, key_field)
        
        # Find uncached keys (deduplicated)
        uncached_keys = list(set(
            k for k in key_values
            if k is not None and k not in self._cache[cache_key]
        ))
        
        # Batch query for uncached keys
        if uncached_keys:
            key_column = getattr(model, key_field)
            entities = self.session.query(model).filter(
                key_column.in_(uncached_keys)
            ).all()
            
            # Populate cache with found entities
            for entity in entities:
                entity_key = getattr(entity, key_field)
                self._cache[cache_key][entity_key] = entity
            
            # Mark missing keys as None in cache
            found_keys = {getattr(e, key_field) for e in entities}
            for key in uncached_keys:
                if key not in found_keys:
                    self._cache[cache_key][key] = None
        
        # Return results in original order
        return [
            self._cache[cache_key].get(k) if k is not None else None
            for k in key_values
        ]
    
    def prime(
        self,
        model: Type[T],
        entity: T,
        key_field: str = "id"
    ) -> None:
        """
        Manually add an entity to the cache.
        
        Useful when you already have an entity and want to
        make it available for future loads.
        
        Args:
            model: SQLAlchemy model class
            entity: Entity instance to cache
            key_field: Column name used as key
        """
        cache_key = self._get_cache_key(model, key_field)
        key_value = getattr(entity, key_field)
        self._cache[cache_key][key_value] = entity
    
    def prime_many(
        self,
        model: Type[T],
        entities: List[T],
        key_field: str = "id"
    ) -> None:
        """
        Manually add multiple entities to the cache.
        
        Args:
            model: SQLAlchemy model class
            entities: List of entity instances to cache
            key_field: Column name used as key
        """
        for entity in entities:
            self.prime(model, entity, key_field)
    
    def clear(self, model: Optional[Type[T]] = None) -> None:
        """
        Clear the cache.
        
        Args:
            model: If provided, only clear cache for this model.
                   Otherwise, clear entire cache.
        """
        if model:
            table_name = model.__tablename__
            keys_to_clear = [
                k for k in self._cache.keys()
                if table_name in k
            ]
            for key in keys_to_clear:
                self._cache[key].clear()
        else:
            self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = sum(len(v) for v in self._cache.values())
        return {
            "models_cached": len(self._cache),
            "total_entries": total_entries,
            "cache_keys": list(self._cache.keys())
        }


class AsyncDataLoader(Generic[T, K]):
    """
    Asynchronous DataLoader with automatic batching.
    
    Collects load requests within the same event loop tick
    and executes them in a single batch query.
    
    Features:
        - Automatic batching within event loop tick
        - Per-request caching
        - Async-native operations
        - Order preservation
    
    Usage:
        >>> loader = AsyncDataLoader(async_session)
        >>> 
        >>> # These will be batched together
        >>> courier1 = await loader.load(CourierModel, "c1")
        >>> courier2 = await loader.load(CourierModel, "c2")
        >>> 
        >>> # Explicit batch
        >>> couriers = await loader.load_many(CourierModel, ["c1", "c2", "c3"])
    """
    
    def __init__(self, session: Any):  # AsyncSession
        """
        Initialize AsyncDataLoader.
        
        Args:
            session: SQLAlchemy AsyncSession
        """
        self.session = session
        self._cache: Dict[str, Dict[Any, Any]] = defaultdict(dict)
        self._batch_queue: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._pending: Dict[str, asyncio.Future] = {}
    
    def _get_cache_key(self, model: Type[T], key_field: str) -> str:
        """Generate unique cache key for model+field combination."""
        return f"{model.__tablename__}:{key_field}"
    
    async def load(
        self,
        model: Type[T],
        key_value: K,
        key_field: str = "id"
    ) -> Optional[T]:
        """
        Load a single entity by key.
        
        Multiple calls within the same event loop tick will be
        automatically batched together.
        
        Args:
            model: SQLAlchemy model class
            key_value: Value to search for
            key_field: Column name to search by
            
        Returns:
            Model instance or None if not found
        """
        if key_value is None:
            return None
        
        loader_key = self._get_cache_key(model, key_field)
        
        # Check cache
        if key_value in self._cache[loader_key]:
            return self._cache[loader_key][key_value]
        
        # Add to batch queue
        if "model" not in self._batch_queue[loader_key]:
            self._batch_queue[loader_key]["model"] = model
            self._batch_queue[loader_key]["key_field"] = key_field
            self._batch_queue[loader_key]["keys"] = []
        
        if key_value not in self._batch_queue[loader_key]["keys"]:
            self._batch_queue[loader_key]["keys"].append(key_value)
        
        # Schedule batch execution
        if loader_key not in self._pending:
            self._pending[loader_key] = asyncio.ensure_future(
                self._execute_batch(loader_key)
            )
        
        await self._pending[loader_key]
        
        return self._cache[loader_key].get(key_value)
    
    async def load_many(
        self,
        model: Type[T],
        key_values: Sequence[K],
        key_field: str = "id"
    ) -> List[Optional[T]]:
        """
        Load multiple entities by keys.
        
        Args:
            model: SQLAlchemy model class
            key_values: List of values to search for
            key_field: Column name to search by
            
        Returns:
            List of model instances (None for missing keys)
        """
        if not key_values:
            return []
        
        # Use gather for parallel loading
        results = await asyncio.gather(*[
            self.load(model, key, key_field)
            for key in key_values
        ])
        
        return list(results)
    
    async def _execute_batch(self, loader_key: str) -> None:
        """Execute batched query after event loop tick."""
        # Allow other loads to queue up
        await asyncio.sleep(0)
        
        batch = self._batch_queue.pop(loader_key, None)
        if not batch or "keys" not in batch:
            if loader_key in self._pending:
                del self._pending[loader_key]
            return
        
        model = batch["model"]
        key_field = batch["key_field"]
        keys = batch["keys"]
        
        # Execute batch query
        key_column = getattr(model, key_field)
        
        try:
            result = await self.session.execute(
                select(model).where(key_column.in_(keys))
            )
            entities = result.scalars().all()
            
            # Populate cache
            for entity in entities:
                entity_key = getattr(entity, key_field)
                self._cache[loader_key][entity_key] = entity
            
            # Mark missing keys as None
            found_keys = {getattr(e, key_field) for e in entities}
            for key in keys:
                if key not in found_keys:
                    self._cache[loader_key][key] = None
                    
        except Exception as e:
            logger.error(f"AsyncDataLoader batch query failed: {e}")
            raise
        finally:
            if loader_key in self._pending:
                del self._pending[loader_key]
    
    def prime(
        self,
        model: Type[T],
        entity: T,
        key_field: str = "id"
    ) -> None:
        """Manually add an entity to the cache."""
        cache_key = self._get_cache_key(model, key_field)
        key_value = getattr(entity, key_field)
        self._cache[cache_key][key_value] = entity
    
    def clear(self, model: Optional[Type[T]] = None) -> None:
        """Clear the cache."""
        if model:
            table_name = model.__tablename__
            keys_to_clear = [
                k for k in self._cache.keys()
                if table_name in k
            ]
            for key in keys_to_clear:
                self._cache[key].clear()
        else:
            self._cache.clear()


def create_dataloader(session: Any) -> Union[SyncDataLoader, AsyncDataLoader]:
    """
    Create appropriate DataLoader based on session type.
    
    Args:
        session: SQLAlchemy Session or AsyncSession
        
    Returns:
        SyncDataLoader or AsyncDataLoader instance
        
    Example:
        >>> loader = create_dataloader(session)
        >>> if isinstance(loader, AsyncDataLoader):
        >>>     result = await loader.load(Model, id)
        >>> else:
        >>>     result = loader.load(Model, id)
    """
    # Check if it's an async session
    session_type = type(session).__name__
    
    if 'Async' in session_type:
        return AsyncDataLoader(session)
    
    return SyncDataLoader(session)
