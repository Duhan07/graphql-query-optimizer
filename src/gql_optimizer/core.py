"""
Core QueryOptimizer implementation.

The main class for optimizing GraphQL queries with SQLAlchemy.
"""

from typing import (
    Any, Dict, List, Optional, Set, Type, Union, Callable
)
import logging

from sqlalchemy.orm import Session, Query, selectinload, joinedload
from sqlalchemy import asc, desc, select

from .utils import (
    GraphQLLibrary,
    detect_graphql_library,
    camel_to_snake,
    get_model_columns,
    get_model_relationships,
    merge_fields,
    validate_model,
    generate_cache_key
)
from .cache import get_cache, QueryCache
from .extractors import FieldExtractor
from .exceptions import (
    SessionNotFoundError,
    InvalidModelError
)

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """
    Advanced GraphQL Query Optimizer for SQLAlchemy.
    
    Automatically optimizes database queries based on GraphQL
    field selections, reducing data transfer and improving performance.
    
    Features:
        - Field selection optimization (only query requested columns)
        - Query caching with TTL
        - Nested fields support
        - Sync and Async support
        - Multiple GraphQL library support
    
    Supported Libraries:
        - Strawberry (recommended)
        - Graphene
        - Ariadne
    
    Usage:
        Basic:
            >>> opt = QueryOptimizer(info, OrderModel, session)
            >>> orders = opt.get_many(limit=10)
        
        With caching:
            >>> opt = QueryOptimizer(info, OrderModel, session, cache=True)
            >>> orders = opt.get_many(limit=10)  # First: DB
            >>> orders = opt.get_many(limit=10)  # Second: Cache
        
        With always included fields:
            >>> opt = QueryOptimizer(
            >>>     info, OrderModel, session,
            >>>     always_include=["id", "created_at"]
            >>> )
        
        Async:
            >>> opt = QueryOptimizer(info, OrderModel, async_session)
            >>> orders = await opt.get_many_async(limit=10)
    
    Performance Tips:
        - Use cache=True for read-heavy endpoints
        - Set appropriate cache_ttl based on data freshness needs
        - Use always_include for fields needed by DataLoader
        - Create new optimizer instance per request
    """
    
    def __init__(
        self,
        info: Any,
        model: Type,
        session: Optional[Any] = None,
        always_include: Optional[List[str]] = None,
        cache: bool = False,
        cache_ttl: int = 60,
        optimize_nested: bool = False,
        custom_cache: Optional[QueryCache] = None
    ):
        """
        Initialize QueryOptimizer.
        
        Args:
            info: GraphQL resolver info object
            model: SQLAlchemy model class
            session: SQLAlchemy Session or AsyncSession
            always_include: Fields to always include (default: ["id"])
            cache: Enable query caching (default: False)
            cache_ttl: Cache TTL in seconds (default: 60)
            optimize_nested: Optimize nested relationship queries
            custom_cache: Custom QueryCache instance
            
        Raises:
            InvalidModelError: If model is not a valid SQLAlchemy model
            SessionNotFoundError: If session cannot be found
        """
        # Validate model
        if not validate_model(model):
            raise InvalidModelError(str(type(model)))
        
        self.info = info
        self.model = model
        self.always_include = set(always_include or ["id"])
        self.use_cache = cache
        self.cache_ttl = cache_ttl
        self.optimize_nested = optimize_nested
        self._cache = custom_cache or get_cache()
        
        # Detect library
        self.library = detect_graphql_library(info)
        
        # Get session
        self.session = session or self._get_session_from_context()
        if self.session is None:
            raise SessionNotFoundError()
        
        # Check if async
        self.is_async = 'Async' in type(self.session).__name__
        
        # Lazy-loaded properties
        self._model_columns: Optional[Set[str]] = None
        self._requested_fields: Optional[Set[str]] = None
        self._valid_fields: Optional[Set[str]] = None
        self._extractor: Optional[FieldExtractor] = None
    
    # ==================== PROPERTIES ====================
    
    @property
    def model_columns(self) -> Set[str]:
        """Get all column names from model."""
        if self._model_columns is None:
            self._model_columns = get_model_columns(self.model)
        return self._model_columns
    
    @property
    def extractor(self) -> FieldExtractor:
        """Get field extractor instance."""
        if self._extractor is None:
            self._extractor = FieldExtractor(
                self.info, 
                self.model, 
                self.library
            )
        return self._extractor
    
    @property
    def requested_fields(self) -> Set[str]:
        """Get fields requested in GraphQL query."""
        if self._requested_fields is None:
            self._requested_fields = self.extractor.extract()
        return self._requested_fields
    
    @property
    def valid_fields(self) -> Set[str]:
        """Get valid fields (requested + always_include, filtered by model)."""
        if self._valid_fields is None:
            self._valid_fields = merge_fields(
                self.requested_fields,
                self.always_include,
                self.model_columns
            )
        return self._valid_fields
    
    # ==================== HELPERS ====================
    
    def _get_session_from_context(self) -> Optional[Any]:
        """Try to get session from GraphQL context."""
        if not hasattr(self.info, 'context'):
            return None
        
        context = self.info.context
        
        # Dict-like context
        if hasattr(context, 'get'):
            return (
                context.get('session') or
                context.get('db') or
                context.get('database')
            )
        
        # Object context
        for attr in ('session', 'db', 'database'):
            if hasattr(context, attr):
                return getattr(context, attr)
        
        return None
    
    def _get_columns(self) -> List:
        """Get SQLAlchemy column objects for valid fields."""
        return [
            getattr(self.model, field)
            for field in self.valid_fields
            if hasattr(self.model, field)
        ]
    
    def _get_cache_key(
        self,
        filters: Optional[Dict] = None,
        limit: int = 10,
        offset: int = 0
    ) -> str:
        """Generate cache key for query."""
        return generate_cache_key(
            self.model,
            self.valid_fields,
            filters,
            limit,
            offset
        )
    
    def is_optimized(self) -> bool:
        """Check if query is optimized (not fetching all columns)."""
        return len(self.valid_fields) < len(self.model_columns)
    
    def get_optimization_info(self) -> Dict[str, Any]:
        """Get detailed optimization information."""
        return {
            "library": self.library.name,
            "model": self.model.__tablename__,
            "total_columns": len(self.model_columns),
            "requested_fields": sorted(self.requested_fields),
            "valid_fields": sorted(self.valid_fields),
            "selected_columns": len(self.valid_fields),
            "is_optimized": self.is_optimized(),
            "cache_enabled": self.use_cache,
            "cache_ttl": self.cache_ttl,
            "is_async": self.is_async
        }
    
    # ==================== QUERY BUILDING ====================
    
    def query(self) -> Query:
        """
        Build optimized SQLAlchemy Query.
        
        Returns:
            SQLAlchemy Query object with only requested columns
        """
        columns = self._get_columns()
        
        if columns and self.is_optimized():
            return self.session.query(*columns)
        else:
            return self.session.query(self.model)
    
    def query_with_options(self, *options) -> Query:
        """
        Build query with additional SQLAlchemy options.
        
        Args:
            *options: SQLAlchemy query options (e.g., joinedload)
            
        Returns:
            SQLAlchemy Query object
        """
        q = self.session.query(self.model)
        for opt in options:
            q = q.options(opt)
        return q
    
    # ==================== RESULT CONVERSION ====================
    
    def to_model(self, row: Any) -> Optional[Any]:
        """
        Convert query result row to model instance.
        
        Args:
            row: Query result row (tuple or model instance)
            
        Returns:
            Model instance or None
        """
        if row is None:
            return None
        
        # Already a model instance
        if hasattr(row, '__table__'):
            return row
        
        # Tuple result - convert to model
        field_list = list(self.valid_fields)
        data = dict(zip(field_list, row))
        
        instance = self.model()
        for key, value in data.items():
            setattr(instance, key, value)
        
        return instance
    
    def to_model_list(self, rows: List) -> List[Any]:
        """Convert multiple rows to model instances."""
        return [self.to_model(row) for row in rows if row is not None]
    
    def to_dict(self, row: Any) -> Optional[Dict[str, Any]]:
        """
        Convert query result row to dictionary.
        
        Args:
            row: Query result row
            
        Returns:
            Dictionary or None
        """
        if row is None:
            return None
        
        if hasattr(row, '__table__'):
            return {
                col.key: getattr(row, col.key)
                for col in row.__table__.columns
            }
        
        field_list = list(self.valid_fields)
        return dict(zip(field_list, row))
    
    def to_dict_list(self, rows: List) -> List[Dict[str, Any]]:
        """Convert multiple rows to dictionaries."""
        return [self.to_dict(row) for row in rows if row is not None]
    
    # ==================== SYNC METHODS ====================
    
    def get_one(
        self,
        filter_condition: Any = None,
        as_model: bool = True
    ) -> Optional[Any]:
        """
        Get a single record.
        
        Args:
            filter_condition: SQLAlchemy filter expression
            as_model: Return as model instance (True) or dict (False)
            
        Returns:
            Model instance, dict, or None
            
        Example:
            >>> order = opt.get_one(OrderModel.order_id == "ORD-123")
        """
        q = self.query()
        
        if filter_condition is not None:
            q = q.filter(filter_condition)
        
        row = q.first()
        
        return self.to_model(row) if as_model else self.to_dict(row)
    
    def get_many(
        self,
        filter_condition: Any = None,
        order_by: Any = None,
        order_direction: str = "desc",
        limit: int = 10,
        offset: int = 0,
        as_model: bool = True
    ) -> List[Any]:
        """
        Get multiple records with optional filtering, ordering, and pagination.
        
        Args:
            filter_condition: SQLAlchemy filter expression
            order_by: Column to order by
            order_direction: "asc" or "desc"
            limit: Maximum records to return
            offset: Number of records to skip
            as_model: Return as model instances (True) or dicts (False)
            
        Returns:
            List of model instances or dicts
            
        Example:
            >>> orders = opt.get_many(
            >>>     filter_condition=(OrderModel.status == "PENDING"),
            >>>     order_by=OrderModel.created_at,
            >>>     limit=20
            >>> )
        """
        # Check cache
        if self.use_cache:
            cache_key = self._get_cache_key(
                {"filter": str(filter_condition)},
                limit,
                offset
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Build query
        q = self.query()
        
        if filter_condition is not None:
            q = q.filter(filter_condition)
        
        if order_by is not None:
            if order_direction == "asc":
                q = q.order_by(asc(order_by))
            else:
                q = q.order_by(desc(order_by))
        
        q = q.limit(limit).offset(offset)
        rows = q.all()
        
        # Convert results
        result = self.to_model_list(rows) if as_model else self.to_dict_list(rows)
        
        # Store in cache
        if self.use_cache:
            self._cache.set(cache_key, result, self.cache_ttl)
        
        return result
    
    def count(self, filter_condition: Any = None) -> int:
        """
        Count records matching filter.
        
        Args:
            filter_condition: SQLAlchemy filter expression
            
        Returns:
            Number of matching records
        """
        from sqlalchemy import func
        
        q = self.session.query(func.count(self.model.id))
        
        if filter_condition is not None:
            q = q.filter(filter_condition)
        
        return q.scalar() or 0
    
    def exists(self, filter_condition: Any) -> bool:
        """
        Check if any record matches filter.
        
        Args:
            filter_condition: SQLAlchemy filter expression
            
        Returns:
            True if at least one record exists
        """
        q = self.session.query(self.model.id).filter(filter_condition).limit(1)
        return q.first() is not None
    
    # ==================== ASYNC METHODS ====================
    
    async def get_one_async(
        self,
        filter_condition: Any = None,
        as_model: bool = True
    ) -> Optional[Any]:
        """
        Get a single record (async).
        
        Args:
            filter_condition: SQLAlchemy filter expression
            as_model: Return as model instance (True) or dict (False)
            
        Returns:
            Model instance, dict, or None
        """
        columns = self._get_columns()
        
        if columns and self.is_optimized():
            stmt = select(*columns)
        else:
            stmt = select(self.model)
        
        if filter_condition is not None:
            stmt = stmt.where(filter_condition)
        
        result = await self.session.execute(stmt)
        row = result.first()
        
        if row is None:
            return None
        
        if self.is_optimized():
            if as_model:
                instance = self.model()
                for key, value in zip(self.valid_fields, row):
                    setattr(instance, key, value)
                return instance
            return dict(zip(self.valid_fields, row))
        else:
            return row[0] if as_model else self.to_dict(row[0])
    
    async def get_many_async(
        self,
        filter_condition: Any = None,
        order_by: Any = None,
        order_direction: str = "desc",
        limit: int = 10,
        offset: int = 0,
        as_model: bool = True
    ) -> List[Any]:
        """
        Get multiple records with optional filtering, ordering, and pagination (async).
        
        Args:
            filter_condition: SQLAlchemy filter expression
            order_by: Column to order by
            order_direction: "asc" or "desc"
            limit: Maximum records to return
            offset: Number of records to skip
            as_model: Return as model instances (True) or dicts (False)
            
        Returns:
            List of model instances or dicts
        """
        # Check cache
        if self.use_cache:
            cache_key = self._get_cache_key(
                {"filter": str(filter_condition)},
                limit,
                offset
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Build statement
        columns = self._get_columns()
        
        if columns and self.is_optimized():
            stmt = select(*columns)
        else:
            stmt = select(self.model)
        
        if filter_condition is not None:
            stmt = stmt.where(filter_condition)
        
        if order_by is not None:
            if order_direction == "asc":
                stmt = stmt.order_by(asc(order_by))
            else:
                stmt = stmt.order_by(desc(order_by))
        
        stmt = stmt.limit(limit).offset(offset)
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        # Convert results
        if self.is_optimized():
            field_list = list(self.valid_fields)
            if as_model:
                results = []
                for row in rows:
                    instance = self.model()
                    for key, value in zip(field_list, row):
                        setattr(instance, key, value)
                    results.append(instance)
            else:
                results = [dict(zip(field_list, row)) for row in rows]
        else:
            if as_model:
                results = [row[0] for row in rows]
            else:
                results = [self.to_dict(row[0]) for row in rows]
        
        # Store in cache
        if self.use_cache:
            self._cache.set(cache_key, results, self.cache_ttl)
        
        return results
    
    async def count_async(self, filter_condition: Any = None) -> int:
        """Count records matching filter (async)."""
        from sqlalchemy import func
        
        stmt = select(func.count()).select_from(self.model)
        
        if filter_condition is not None:
            stmt = stmt.where(filter_condition)
        
        result = await self.session.execute(stmt)
        return result.scalar() or 0
    
    async def exists_async(self, filter_condition: Any) -> bool:
        """Check if any record matches filter (async)."""
        stmt = select(self.model.id).where(filter_condition).limit(1)
        result = await self.session.execute(stmt)
        return result.first() is not None


# ==================== CONVENIENCE FUNCTIONS ====================

def optimize(
    info: Any,
    model: Type,
    session: Any = None,
    **kwargs
) -> QueryOptimizer:
    """
    Create a QueryOptimizer instance (shortcut).
    
    Args:
        info: GraphQL resolver info object
        model: SQLAlchemy model class
        session: Database session
        **kwargs: Additional QueryOptimizer arguments
        
    Returns:
        QueryOptimizer instance
        
    Example:
        >>> from gql_optimizer import optimize
        >>> 
        >>> @strawberry.field
        >>> def orders(self, info: Info) -> List[Order]:
        >>>     opt = optimize(info, OrderModel, session, cache=True)
        >>>     return opt.get_many(limit=10)
    """
    return QueryOptimizer(info, model, session, **kwargs)
