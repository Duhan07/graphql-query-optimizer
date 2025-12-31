# GraphQL Query Optimizer for SQLAlchemy

[![PyPI version](https://badge.fury.io/py/gql-optimizer.svg)](https://badge.fury.io/py/gql-optimizer)
[![Python versions](https://img.shields.io/pypi/pyversions/gql-optimizer.svg)](https://pypi.org/project/gql-optimizer/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/Duhan07/graphql-query-optimizer/workflows/tests/badge.svg)](https://github.com/Duhan07/graphql-query-optimizer/actions)

A powerful library for optimizing GraphQL queries with SQLAlchemy. Automatically selects only the requested fields, implements caching, and provides DataLoader for N+1 problem prevention.

## Features

- ✅ **Field Selection Optimization** - Only query columns that are requested in GraphQL
- ✅ **Query Caching** - Built-in LRU cache with TTL support
- ✅ **DataLoader** - Batch loading to solve N+1 query problem
- ✅ **Async Support** - Full async/await support for async SQLAlchemy
- ✅ **Multiple Libraries** - Works with Strawberry, Graphene, and Ariadne
- ✅ **Type Safe** - Full type hints for IDE support

## Installation

### Using pip

```bash
# Basic installation
pip install gql-optimizer

# With Strawberry support (recommended)
pip install "gql-optimizer[strawberry]"

# With Graphene support
pip install "gql-optimizer[graphene]"

# With Ariadne support
pip install "gql-optimizer[ariadne]"

# With async support
pip install "gql-optimizer[async]"

# All extras (all frameworks + async)
pip install "gql-optimizer[all]"
```

### Using uv (Recommended)

```bash
# Basic installation
uv add gql-optimizer

# With Strawberry support (recommended)
uv add "gql-optimizer[strawberry]"

# With Graphene support
uv add "gql-optimizer[graphene]"

# With Ariadne support
uv add "gql-optimizer[ariadne]"

# With async support
uv add "gql-optimizer[async]"

# All extras (all frameworks + async)
uv add "gql-optimizer[all]"
```

### Available Extras

| Extra | Description | Includes |
|-------|-------------|----------|
| `strawberry` | Strawberry GraphQL support | strawberry-graphql |
| `graphene` | Graphene support | graphene |
| `ariadne` | Ariadne support | ariadne |
| `async` | Async SQLAlchemy support | aiosqlite, greenlet |
| `all` | All frameworks + async | All above |
| `dev` | Development tools | pytest, black, mypy, build, twine |
| `docs` | Documentation | mkdocs, mkdocs-material |

## Quick Start

### Basic Usage

```python
from gql_optimizer import QueryOptimizer
import strawberry
from strawberry.types import Info
from typing import List

@strawberry.type
class Query:
    @strawberry.field
    def orders(self, info: Info, limit: int = 10) -> List[Order]:
        session = get_session()
        
        # Create optimizer
        opt = QueryOptimizer(info, OrderModel, session)
        
        # Get optimized results
        return opt.get_many(limit=limit)
```

**What happens:**

```graphql
# GraphQL Query
query {
  orders(limit: 10) {
    id
    orderId
    totalPrice
  }
}
```

```sql
-- Generated SQL (only requested columns!)
SELECT id, order_id, total_price FROM orders LIMIT 10

-- Instead of:
-- SELECT id, order_id, total_price, status, courier_id, 
--        basket_id, created_at, ... (50+ columns) FROM orders
```

### With Caching

```python
@strawberry.field
def orders(self, info: Info, limit: int = 10) -> List[Order]:
    opt = QueryOptimizer(
        info, 
        OrderModel, 
        session,
        cache=True,      # Enable caching
        cache_ttl=60     # Cache for 60 seconds
    )
    
    return opt.get_many(limit=limit)
```

### With DataLoader (N+1 Prevention)

```python
from gql_optimizer import QueryOptimizer, SyncDataLoader

@strawberry.field
def orders_with_details(self, info: Info) -> List[Order]:
    session = get_session()
    loader = SyncDataLoader(session)
    
    # Get orders with courier_id included
    opt = QueryOptimizer(
        info, 
        OrderModel, 
        session,
        always_include=["id", "courier_id", "basket_id"]
    )
    
    orders = opt.get_many(limit=10)
    
    # Batch load related data (single query each!)
    courier_ids = [o.courier_id for o in orders if o.courier_id]
    basket_ids = [o.basket_id for o in orders if o.basket_id]
    
    courier_map = {
        c.id: c for c in loader.load_many(CourierModel, courier_ids)
        if c
    }
    basket_map = {
        b.basket_id: b for b in loader.load_many(
            BasketModel, basket_ids, key_field="basket_id"
        )
        if b
    }
    
    # Attach relationships
    for order in orders:
        order.courier = courier_map.get(order.courier_id)
        order.basket = basket_map.get(order.basket_id)
    
    return orders
```

**Result:**
```sql
-- Only 3 queries instead of N+1!
SELECT ... FROM orders LIMIT 10
SELECT ... FROM couriers WHERE id IN (...)
SELECT ... FROM baskets WHERE basket_id IN (...)
```

### Async Usage

```python
from gql_optimizer import QueryOptimizer, AsyncDataLoader

@strawberry.field
async def orders(self, info: Info) -> List[Order]:
    async with AsyncSessionLocal() as session:
        opt = QueryOptimizer(info, OrderModel, session, cache=True)
        return await opt.get_many_async(limit=10)
```

## API Reference

### QueryOptimizer

```python
QueryOptimizer(
    info,                    # GraphQL info object
    model,                   # SQLAlchemy model class
    session=None,            # Database session (optional if in context)
    always_include=["id"],   # Fields to always include
    cache=False,             # Enable caching
    cache_ttl=60,            # Cache TTL in seconds
    optimize_nested=False    # Optimize nested relationships
)
```

#### Methods

| Method | Description |
|--------|-------------|
| `get_one(filter, as_model=True)` | Get single record |
| `get_many(filter, order_by, limit, offset)` | Get multiple records |
| `get_one_async(...)` | Async version of get_one |
| `get_many_async(...)` | Async version of get_many |
| `query()` | Get raw SQLAlchemy Query |
| `count(filter)` | Count matching records |
| `exists(filter)` | Check if records exist |

### SyncDataLoader

```python
loader = SyncDataLoader(session)

# Single load
courier = loader.load(CourierModel, "courier_123")

# Batch load
couriers = loader.load_many(CourierModel, ["c1", "c2", "c3"])

# Custom key field
order = loader.load(OrderModel, "ORD-123", key_field="order_id")
```

### AsyncDataLoader

```python
loader = AsyncDataLoader(async_session)

# Single load (async)
courier = await loader.load(CourierModel, "courier_123")

# Batch load (async)
couriers = await loader.load_many(CourierModel, ["c1", "c2", "c3"])
```

### QueryCache

```python
from gql_optimizer import get_cache, clear_cache, configure_cache

# Get global cache
cache = get_cache()

# Clear all cache
clear_cache()

# Configure cache
configure_cache(ttl_seconds=120, max_size=2000)

# Cache stats
stats = cache.stats()
# {'size': 45, 'max_size': 1000, 'hit_rate': 87.5, ...}
```

## Framework Support

### Strawberry (Recommended)

```python
import strawberry
from strawberry.types import Info
from gql_optimizer import QueryOptimizer

@strawberry.type
class Query:
    @strawberry.field
    def orders(self, info: Info) -> List[Order]:
        opt = QueryOptimizer(info, OrderModel, session)
        return opt.get_many(limit=10)
```

### Graphene

```python
import graphene
from gql_optimizer import QueryOptimizer

class Query(graphene.ObjectType):
    orders = graphene.List(OrderType)
    
    def resolve_orders(self, info):
        opt = QueryOptimizer(info, OrderModel, session)
        return opt.get_many(limit=10)
```

### Ariadne

```python
from ariadne import QueryType
from gql_optimizer import QueryOptimizer

query = QueryType()

@query.field("orders")
def resolve_orders(_, info):
    opt = QueryOptimizer(info, OrderModel, session)
    return opt.get_many(limit=10)
```

## Performance Comparison

| Scenario | Without Optimizer | With Optimizer |
|----------|------------------|----------------|
| Simple query (10 fields requested) | 50 columns fetched | 10 columns fetched |
| N+1 problem (10 orders + courier) | 11 queries | 2 queries |
| Repeated query | DB hit every time | Cache hit (0ms) |
| Response size | ~50KB | ~10KB |

## Best Practices

### 1. Always Include Foreign Keys

```python
opt = QueryOptimizer(
    info, OrderModel, session,
    always_include=["id", "courier_id", "basket_id"]  # For relationships
)
```

### 2. Use Cache for Read-Heavy Endpoints

```python
opt = QueryOptimizer(
    info, OrderModel, session,
    cache=True,
    cache_ttl=30  # Short TTL for frequently changing data
)
```

### 3. Create New DataLoader Per Request

```python
@strawberry.field
def orders(self, info: Info) -> List[Order]:
    loader = SyncDataLoader(session)  # New loader per request
    # ... use loader
```

### 4. Use Type Hints

```python
from gql_optimizer import QueryOptimizer, SyncDataLoader

def get_orders(info: Info, session: Session) -> List[Order]:
    opt: QueryOptimizer = QueryOptimizer(info, OrderModel, session)
    return opt.get_many(limit=10)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Using pip

```bash
# Clone the repository
git clone https://github.com/Duhan07/graphql-query-optimizer.git
cd graphql-query-optimizer

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src tests
isort src tests

# Type check
mypy src
```

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/Duhan07/graphql-query-optimizer.git
cd graphql-query-optimizer

# Install development dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Format code
uv run black src tests
uv run isort src tests

# Type check
uv run mypy src

# Build package
uv run python -m build

# Upload to PyPI
uv run twine upload dist/*
```

## Requirements

- Python >= 3.9
- SQLAlchemy >= 2.0.0

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes.

## Credits

Created by [Duhan Günsel](https://github.com/Duhan07).

Inspired by the need for efficient GraphQL + SQLAlchemy integration in production applications.