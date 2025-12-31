"""
GraphQL Query Optimizer for SQLAlchemy.

A powerful library for optimizing GraphQL queries with SQLAlchemy,
supporting multiple GraphQL libraries (Strawberry, Graphene, Ariadne).

Features:
    - Field selection optimization (only query requested columns)
    - Query caching with TTL and LRU eviction
    - DataLoader for N+1 problem prevention
    - Sync and Async support
    - Multiple GraphQL library support

Quick Start:
    >>> from gql_optimizer import QueryOptimizer
    >>>
    >>> @strawberry.field
    >>> def orders(self, info: Info) -> List[Order]:
    >>>     opt = QueryOptimizer(info, OrderModel, session, cache=True)
    >>>     return opt.get_many(limit=10)

With DataLoader:
    >>> from gql_optimizer import QueryOptimizer, SyncDataLoader
    >>>
    >>> @strawberry.field
    >>> def orders_with_details(self, info: Info) -> List[Order]:
    >>>     loader = SyncDataLoader(session)
    >>>     opt = QueryOptimizer(
    >>>         info, OrderModel, session,
    >>>         always_include=["id", "courier_id"]
    >>>     )
    >>>
    >>>     orders = opt.get_many(limit=10)
    >>>
    >>>     # Batch load couriers
    >>>     courier_ids = [o.courier_id for o in orders if o.courier_id]
    >>>     couriers = loader.load_many(CourierModel, courier_ids)
    >>>
    >>>     return orders

Documentation:
    https://github.com/Duhan07/graphql-query-optimizer

License:
    MIT License
"""

__version__ = "1.0.0"
__author__ = "Duhan Günsel"
__email__ = "gnsl.duhan.07@gmail.com"

# Core optimizer
# Cache
from .cache import (
    QueryCache,
    clear_cache,
    configure_cache,
    get_cache,
)
from .core import (
    QueryOptimizer,
    optimize,
)

# DataLoader
from .dataloader import (
    AsyncDataLoader,
    SyncDataLoader,
    create_dataloader,
)

# Exceptions
from .exceptions import (
    CacheError,
    DataLoaderError,
    FieldExtractionError,
    GQLOptimizerError,
    InvalidModelError,
    SessionNotFoundError,
    UnsupportedLibraryError,
)

# Field extraction
from .extractors import (
    FieldExtractor,
    extract_fields,
)

# Utilities
from .utils import (
    GraphQLLibrary,
    camel_to_snake,
    detect_graphql_library,
    get_model_columns,
    get_model_relationships,
    snake_to_camel,
)

# Public API
__all__ = [
    # Version
    "__version__",
    # Core
    "QueryOptimizer",
    "optimize",
    # Cache
    "QueryCache",
    "get_cache",
    "clear_cache",
    "configure_cache",
    # DataLoader
    "SyncDataLoader",
    "AsyncDataLoader",
    "create_dataloader",
    # Extractors
    "FieldExtractor",
    "extract_fields",
    # Utilities
    "GraphQLLibrary",
    "camel_to_snake",
    "snake_to_camel",
    "detect_graphql_library",
    "get_model_columns",
    "get_model_relationships",
    # Exceptions
    "GQLOptimizerError",
    "SessionNotFoundError",
    "InvalidModelError",
    "FieldExtractionError",
    "CacheError",
    "DataLoaderError",
    "UnsupportedLibraryError",
]
